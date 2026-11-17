"""Điều phối quy trình. Mỗi lần chạy có thư mục kết quả riêng theo Run ID.

Luồng: tạo thư mục run -> kiểm tra đầu vào + băm SHA-256 -> nạp (DuckDB, có giới hạn bộ nhớ và thư mục temp)
-> kiểm tra Time Completed -> phân loại -> ghi Parquet -> kiểm tra RAW không đổi -> đối soát -> Excel + manifest.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional, Sequence, Union

import duckdb

from . import audit, summary
from .config import (
    CLEAN_FILE_NAME,
    DEFAULT_MEMORY_LIMIT,
    ENV_MEMORY_LIMIT,
    ENV_TEMP_DIR,
    ENV_THREADS,
    EXPECTED_COLUMNS,
    LOG_FILE_NAME,
    MANIFEST_FILE_NAME,
    REMOVED_FILE_NAME,
    REPORT_MONTH_COLUMN,
    SOURCE_COLUMN,
    SUMMARY_FILE_NAME,
    TEMP_DIR_NAME,
)
from .errors import (
    CleaningError,
    DataFormatError,
    RawIntegrityError,
    ReconciliationError,
    RunFolderError,
)
from .ingest import InputFile, source_select, validate_inputs
from .rules import RULES, Rule, any_flag_sql, flag_column, quote_ident, report_month_expr, sql_str

logger = logging.getLogger("cleaning")

ProgressCallback = Callable[[str, str, Optional[float]], None]
PathLike = Union[str, Path]


@dataclass(frozen=True)
class EngineSettings:
    """Giới hạn tài nguyên cho DuckDB.

    memory_limit: ví dụ "2GB". Vượt quá thì DuckDB tràn ra thư mục temp.
    temp_directory: thư mục temp. Mặc định nằm trong thư mục Run và bị xóa khi kết thúc.
    threads: số luồng. None nghĩa là để DuckDB tự chọn.
    """

    memory_limit: str = DEFAULT_MEMORY_LIMIT
    temp_directory: Optional[Path] = None
    threads: Optional[int] = None

    @classmethod
    def from_env(cls) -> "EngineSettings":
        temp = os.environ.get(ENV_TEMP_DIR)
        threads = os.environ.get(ENV_THREADS)
        return cls(
            memory_limit=os.environ.get(ENV_MEMORY_LIMIT, DEFAULT_MEMORY_LIMIT),
            temp_directory=Path(temp) if temp else None,
            threads=int(threads) if threads else None,
        )

    def as_dict(self) -> dict:
        return {
            "memory_limit": self.memory_limit,
            "temp_directory": self.temp_directory.as_posix() if self.temp_directory else None,
            "threads": self.threads,
        }


@dataclass(frozen=True)
class CleaningResult:
    run_id: str
    run_dir: Path
    clean_path: Path
    removed_path: Path
    summary_path: Path
    manifest_path: Path
    stats: summary.RunStats


@dataclass
class FileCheck:
    name: str
    encoding: str
    rows: int
    invalid_time_completed: int
    months: list[str]


@dataclass
class PrecheckResult:
    files: list[FileCheck] = field(default_factory=list)

    @property
    def rows_total(self) -> int:
        return sum(f.rows for f in self.files)

    @property
    def invalid_total(self) -> int:
        return sum(f.invalid_time_completed for f in self.files)

    @property
    def months(self) -> list[str]:
        return sorted({m for f in self.files for m in f.months})

    @property
    def ok(self) -> bool:
        return self.invalid_total == 0


def _open_connection(settings: EngineSettings, temp_dir: Path) -> duckdb.DuckDBPyConnection:
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"SET memory_limit = {sql_str(settings.memory_limit)}")
        con.execute(f"SET temp_directory = {sql_str(temp_dir.resolve().as_posix())}")
        con.execute("SET preserve_insertion_order = false")
        if settings.threads:
            con.execute(f"SET threads = {int(settings.threads)}")
    except Exception:
        con.close()
        raise
    return con


def precheck(inputs: Sequence[PathLike], settings: Optional[EngineSettings] = None) -> PrecheckResult:
    """Kiểm tra đầu vào mà không ghi kết quả: cấu trúc, encoding, số dòng, tháng, dòng sai Time Completed.

    Lỗi cấu trúc ném InputError. Dòng sai Time Completed được đếm và trả về, không ném lỗi.
    """
    settings = settings or EngineSettings()
    files = validate_inputs([Path(p) for p in inputs])
    base = settings.temp_directory or Path(tempfile.gettempdir()) / "cmit_housekeeping"
    tmp = base / f"precheck_{uuid.uuid4().hex[:8]}"
    con = _open_connection(settings, tmp)
    try:
        union = "\nUNION ALL\n".join(source_select(f) for f in files)
        src = quote_ident(SOURCE_COLUMN)
        rm = quote_ident(REPORT_MONTH_COLUMN)
        rows = con.execute(
            f"SELECT {src}, {rm}, COUNT(*) FROM "
            f"(SELECT *, {report_month_expr()} AS {rm} FROM ({union}) AS s) AS t "
            f"GROUP BY 1, 2"
        ).fetchall()
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)

    counts = {f.name: {"rows": 0, "invalid": 0, "months": set()} for f in files}
    for name, month, count in rows:
        c = counts[name]
        c["rows"] += int(count)
        if month is None:
            c["invalid"] += int(count)
        else:
            c["months"].add(month)

    return PrecheckResult(files=[
        FileCheck(
            name=f.name,
            encoding=f.encoding,
            rows=counts[f.name]["rows"],
            invalid_time_completed=counts[f.name]["invalid"],
            months=sorted(counts[f.name]["months"]),
        )
        for f in files
    ])


class CleaningEngine:
    def __init__(
        self,
        rules: Sequence[Rule] = RULES,
        progress: Optional[ProgressCallback] = None,
        settings: Optional[EngineSettings] = None,
    ) -> None:
        self.rules: tuple[Rule, ...] = tuple(rules)
        self._progress = progress
        self.settings = settings or EngineSettings()
        self._timings: dict[str, float] = {}

    # ------------------------------------------------------------------ API
    def run(
        self,
        inputs: Sequence[PathLike],
        output_base: PathLike,
        run_id: Optional[str] = None,
    ) -> CleaningResult:
        """Chạy một lần làm sạch. Kết quả nằm trong output_base/<run_id>/. Không ghi đè lần chạy cũ."""
        base = Path(output_base)
        base.mkdir(parents=True, exist_ok=True)
        rid = run_id or audit.new_run_id()
        run_dir = base / rid
        try:
            run_dir.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise RunFolderError(f"Thư mục kết quả đã tồn tại, không ghi đè: {run_dir}") from exc

        self._timings = {}
        manifest = audit.RunManifest(rid, run_dir, self.rules)
        manifest.update(settings=self.settings.as_dict())
        handler = logging.FileHandler(run_dir / LOG_FILE_NAME, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            logger.info("Run %s bắt đầu, thư mục: %s", rid, run_dir)
            result = self._run([Path(p) for p in inputs], run_dir, rid, manifest)
            manifest.finish("SUCCESS")
            return result
        except Exception as exc:
            manifest.finish("FAILED", error=f"{type(exc).__name__}: {exc}")
            logger.error("Dừng xử lý: %s", exc)
            raise
        finally:
            manifest.update(timings_seconds=dict(self._timings))
            manifest.write(run_dir / MANIFEST_FILE_NAME)
            logger.removeHandler(handler)
            handler.close()

    # ------------------------------------------------------------- internals
    def _emit(self, stage: str, message: str, fraction: Optional[float] = None) -> None:
        if self._progress is not None:
            self._progress(stage, message, fraction)
        logger.info("[%s] %s", stage, message)

    @contextmanager
    def _timed(self, key: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._timings[key] = round(time.perf_counter() - start, 3)

    def _run(self, inputs: list[Path], run_dir: Path, rid: str, manifest: audit.RunManifest):
        self._emit("validate", "Kiểm tra cấu trúc file đầu vào", 0.0)
        with self._timed("validate"):
            files = validate_inputs(inputs)
            before = {f.name: audit.sha256_file(f.path) for f in files}
        manifest.set_inputs([
            {
                "file": f.name,
                "path": f.path.resolve().as_posix(),
                "size_bytes": f.path.stat().st_size,
                "encoding": f.encoding,
                "column_map": {canon: raw for canon, _, raw in f.column_map},
                "sha256_before": before[f.name],
            }
            for f in files
        ])
        for f in files:
            logger.info("Đầu vào: %s (encoding %s)", f.name, f.encoding)

        clean_path = run_dir / CLEAN_FILE_NAME
        removed_path = run_dir / REMOVED_FILE_NAME
        summary_path = run_dir / SUMMARY_FILE_NAME
        manifest_path = run_dir / MANIFEST_FILE_NAME

        temp_dir = (self.settings.temp_directory / rid) if self.settings.temp_directory else (run_dir / TEMP_DIR_NAME)
        rm = quote_ident(REPORT_MONTH_COLUMN)
        con = _open_connection(self.settings, temp_dir)
        try:
            with self._timed("load"):
                con.execute(
                    f"CREATE TABLE raw_data AS SELECT *, {report_month_expr()} AS {rm} "
                    f"FROM ({self._union_sql(files)}) AS src"
                )
                loaded = con.execute("SELECT COUNT(*) FROM raw_data").fetchone()[0]
            self._emit("load", f"Đã nạp {loaded} dòng từ {len(files)} file", 0.2)

            self._check_time_completed(con)
            self._emit("validate", "Time Completed hợp lệ cho mọi dòng", 0.3)

            con.execute(f"CREATE VIEW classified AS SELECT {self._classified_select()} FROM raw_data")
            with self._timed("write_clean"):
                con.execute(
                    f"COPY ({self._clean_sql()}) TO {sql_str(clean_path.as_posix())} "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
            self._emit("write", "Đã ghi CLEAN_DATA", 0.5)
            with self._timed("write_removed"):
                con.execute(
                    f"COPY ({self._removed_sql()}) TO {sql_str(removed_path.as_posix())} "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
            self._emit("write", "Đã ghi REMOVED_DATA", 0.7)

            with self._timed("stats"):
                stats = summary.collect_stats(con, files, self.rules, clean_path, removed_path, rid)
        finally:
            con.close()
            shutil.rmtree(temp_dir, ignore_errors=True)

        with self._timed("integrity"):
            after = {f.name: audit.sha256_file(f.path) for f in files}
        changed = [name for name in before if before[name] != after[name]]
        if changed:
            raise RawIntegrityError(f"File RAW bị thay đổi trong lúc chạy: {changed}")
        self._emit("integrity", "RAW không thay đổi (SHA-256 trước và sau khớp)", 0.8)

        problems = summary.reconcile(stats)
        with self._timed("summary"):
            summary.write_excel(stats, problems, summary_path)
        self._emit("summary", "Đã ghi cleaning_summary.xlsx", 0.95)

        manifest.update(
            counts={
                "raw_total": stats.raw_total,
                "clean_total": stats.clean_total,
                "removed_total": stats.removed_total,
                "months": [m.month for m in stats.months],
                "reconciliation": "OK" if not problems else "LỖI",
            },
            outputs={
                "clean_data": clean_path.name,
                "removed_data": removed_path.name,
                "summary": summary_path.name,
            },
            temp_dir_removed=not temp_dir.exists(),
        )
        for entry in manifest.data["inputs"]:
            entry["sha256_after"] = after[entry["file"]]

        if problems:
            raise ReconciliationError("Đối soát thất bại:\n - " + "\n - ".join(problems))

        self._emit("done", "Hoàn tất", 1.0)
        return CleaningResult(
            run_id=rid,
            run_dir=run_dir,
            clean_path=clean_path,
            removed_path=removed_path,
            summary_path=summary_path,
            manifest_path=manifest_path,
            stats=stats,
        )

    def _check_time_completed(self, con: duckdb.DuckDBPyConnection) -> None:
        src = quote_ident(SOURCE_COLUMN)
        rm = quote_ident(REPORT_MONTH_COLUMN)
        bad_total = con.execute(f"SELECT COUNT(*) FROM raw_data WHERE {rm} IS NULL").fetchone()[0]
        if not bad_total:
            return
        per_file = con.execute(
            f"SELECT {src}, COUNT(*) FROM raw_data WHERE {rm} IS NULL GROUP BY 1 ORDER BY 1"
        ).fetchall()
        sample = con.execute(
            f"SELECT {src}, {quote_ident('Unit Nbr')}, {quote_ident('Time Completed')} "
            f"FROM raw_data WHERE {rm} IS NULL LIMIT 5"
        ).fetchall()
        raise DataFormatError(
            "Time Completed sai định dạng hoặc không phải ngày hợp lệ. "
            "Yêu cầu dạng yy-Mon-dd HHMM, ví dụ 26-Oct-31 2358. "
            f"Tổng số dòng lỗi: {bad_total}. Theo file: {per_file}. "
            f"Mẫu (file, Unit Nbr, giá trị): {sample}"
        )

    @staticmethod
    def _union_sql(files: Sequence[InputFile]) -> str:
        return "\nUNION ALL\n".join(source_select(f) for f in files)

    def _classified_select(self) -> str:
        flags = ", ".join(
            f"({r.condition}) AS {quote_ident(flag_column(r.rule_id))}" for r in self.rules)
        return f"*, {flags}" if flags else "*"

    def _base_cols(self) -> str:
        cols = (*EXPECTED_COLUMNS, SOURCE_COLUMN, REPORT_MONTH_COLUMN)
        return ", ".join(quote_ident(c) for c in cols)

    def _clean_sql(self) -> str:
        return f"SELECT {self._base_cols()} FROM classified WHERE NOT ({any_flag_sql(self.rules)})"

    def _removed_sql(self) -> str:
        if self.rules:
            rule_ids = "CONCAT_WS('|', " + ", ".join(
                f"CASE WHEN {quote_ident(flag_column(r.rule_id))} THEN {sql_str(r.rule_id)} END"
                for r in self.rules) + ")"
            reasons = "CONCAT_WS('; ', " + ", ".join(
                f"CASE WHEN {quote_ident(flag_column(r.rule_id))} "
                f"THEN {sql_str(r.rule_id + ': ' + r.description)} END"
                for r in self.rules) + ")"
        else:
            rule_ids = reasons = "''"
        return (
            f"SELECT {self._base_cols()}, {rule_ids} AS \"Rule_ID\", {reasons} AS \"Removal_Reason\" "
            f"FROM classified WHERE {any_flag_sql(self.rules)}"
        )
