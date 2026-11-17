"""Thống kê theo file và theo tháng, đối soát, cảnh báo và xuất Excel."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import pandas as pd
from openpyxl.utils import get_column_letter

from .config import (
    COL_MOVE,
    COL_TIME_FETCH,
    DUPLICATE_KEY_COLUMNS,
    KNOWN_MOVE_KINDS,
    REPORT_MONTH_COLUMN,
    SOURCE_COLUMN,
)
from .ingest import InputFile
from .rules import (
    Rule,
    any_flag_sql,
    flag_column,
    norm,
    quote_ident,
    sql_str,
    time_fetch_invalid_sql,
)

if TYPE_CHECKING:
    import duckdb


@dataclass
class FileStats:
    name: str
    raw: int = 0
    removed: int = 0               # từ bảng phân loại
    clean_written: int = 0         # đếm lại từ Parquet đã ghi
    removed_written: int = 0       # đếm lại từ Parquet đã ghi
    months: int = 0
    rule_hits: dict[str, int] = field(default_factory=dict)
    blank_time_of_fetch: int = 0
    invalid_time_of_fetch: int = 0


@dataclass
class MonthStats:
    month: str
    raw: int = 0
    removed: int = 0
    clean_written: int = 0
    removed_written: int = 0


@dataclass
class RunStats:
    run_id: str
    run_at: str
    rules: tuple[Rule, ...]
    files: list[FileStats]
    months: list[MonthStats]
    overlap: dict[int, int]
    duplicate_rows: int
    unknown_move_kinds: list[tuple[str, str, int]]
    clean_path: Path
    removed_path: Path

    @property
    def raw_total(self) -> int:
        return sum(f.raw for f in self.files)

    @property
    def clean_total(self) -> int:
        return sum(f.clean_written for f in self.files)

    @property
    def removed_total(self) -> int:
        return sum(f.removed_written for f in self.files)


def _pairs(rows: list) -> dict:
    return {r[0]: int(r[1] or 0) for r in rows}


def collect_stats(
    con: "duckdb.DuckDBPyConnection",
    files: Sequence[InputFile],
    rules: Sequence[Rule],
    clean_path: Path,
    removed_path: Path,
    run_id: str,
) -> RunStats:
    src = quote_ident(SOURCE_COLUMN)
    rm = quote_ident(REPORT_MONTH_COLUMN)
    any_expr = any_flag_sql(rules)
    clean_sql = sql_str(clean_path.as_posix())
    removed_sql = sql_str(removed_path.as_posix())

    raw_by_file = _pairs(con.execute(f"SELECT {src}, COUNT(*) FROM raw_data GROUP BY 1").fetchall())
    raw_by_month = _pairs(con.execute(f"SELECT {rm}, COUNT(*) FROM raw_data GROUP BY 1").fetchall())
    months_per_file = _pairs(con.execute(
        f"SELECT {src}, COUNT(DISTINCT {rm}) FROM raw_data GROUP BY 1").fetchall())

    hit_exprs = [f"SUM(CAST({quote_ident(flag_column(r.rule_id))} AS INTEGER))" for r in rules]
    rows = con.execute(
        f"SELECT {src}, COUNT(*), SUM(CAST(({any_expr}) AS INTEGER)), {', '.join(hit_exprs)} "
        f"FROM classified GROUP BY 1").fetchall()
    removed_by_file = {r[0]: int(r[2] or 0) for r in rows}
    hits_by_file = {
        r[0]: {rules[i].rule_id: int(r[3 + i] or 0) for i in range(len(rules))} for r in rows
    }
    removed_by_month = _pairs(con.execute(
        f"SELECT {rm}, SUM(CAST(({any_expr}) AS INTEGER)) FROM classified GROUP BY 1").fetchall())

    clean_w_file = _pairs(con.execute(
        f"SELECT {src}, COUNT(*) FROM read_parquet({clean_sql}) GROUP BY 1").fetchall())
    removed_w_file = _pairs(con.execute(
        f"SELECT {src}, COUNT(*) FROM read_parquet({removed_sql}) GROUP BY 1").fetchall())
    clean_w_month = _pairs(con.execute(
        f"SELECT {rm}, COUNT(*) FROM read_parquet({clean_sql}) GROUP BY 1").fetchall())
    removed_w_month = _pairs(con.execute(
        f"SELECT {rm}, COUNT(*) FROM read_parquet({removed_sql}) GROUP BY 1").fetchall())

    blank_tf = _pairs(con.execute(
        f"SELECT {src}, SUM(CASE WHEN {norm(COL_TIME_FETCH)} = '' THEN 1 ELSE 0 END) "
        f"FROM raw_data GROUP BY 1").fetchall())
    invalid_tf = _pairs(con.execute(
        f"SELECT {src}, SUM(CASE WHEN {time_fetch_invalid_sql()} THEN 1 ELSE 0 END) "
        f"FROM raw_data GROUP BY 1").fetchall())

    file_stats = [
        FileStats(
            name=f.name,
            raw=raw_by_file.get(f.name, 0),
            removed=removed_by_file.get(f.name, 0),
            clean_written=clean_w_file.get(f.name, 0),
            removed_written=removed_w_file.get(f.name, 0),
            months=months_per_file.get(f.name, 0),
            rule_hits=hits_by_file.get(f.name, {r.rule_id: 0 for r in rules}),
            blank_time_of_fetch=blank_tf.get(f.name, 0),
            invalid_time_of_fetch=invalid_tf.get(f.name, 0),
        )
        for f in files
    ]

    month_stats = [
        MonthStats(
            month=m,
            raw=raw_by_month[m],
            removed=removed_by_month.get(m, 0),
            clean_written=clean_w_month.get(m, 0),
            removed_written=removed_w_month.get(m, 0),
        )
        for m in sorted(raw_by_month)
    ]

    overlap_expr = " + ".join(
        f"CAST({quote_ident(flag_column(r.rule_id))} AS INTEGER)" for r in rules) or "0"
    overlap = {int(n): int(c) for n, c in con.execute(
        f"SELECT n, COUNT(*) FROM (SELECT ({overlap_expr}) AS n FROM classified) GROUP BY n"
    ).fetchall()}

    keys = ", ".join(quote_ident(c) for c in DUPLICATE_KEY_COLUMNS)
    duplicate_rows = int(con.execute(
        f"SELECT COALESCE(SUM(c - 1), 0) FROM "
        f"(SELECT COUNT(*) AS c FROM raw_data GROUP BY {keys} HAVING COUNT(*) > 1)"
    ).fetchone()[0])

    known = ", ".join(sql_str(k) for k in sorted(KNOWN_MOVE_KINDS))
    mk = norm(COL_MOVE)
    unknown = [
        (r[0], r[1], int(r[2])) for r in con.execute(
            f"SELECT {src}, {mk} AS mk, COUNT(*) FROM raw_data "
            f"WHERE {mk} NOT IN ({known}) GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    ]

    return RunStats(
        run_id=run_id,
        run_at=datetime.now().isoformat(timespec="seconds"),
        rules=tuple(rules),
        files=file_stats,
        months=month_stats,
        overlap=overlap,
        duplicate_rows=duplicate_rows,
        unknown_move_kinds=unknown,
        clean_path=clean_path,
        removed_path=removed_path,
    )


def reconcile(stats: RunStats) -> list[str]:
    """Danh sách lỗi đối soát. Rỗng nghĩa là đạt, theo từng file, từng tháng và toàn bộ."""
    problems: list[str] = []
    for f in stats.files:
        if f.raw != f.clean_written + f.removed_written:
            problems.append(
                f"File {f.name}: Raw {f.raw} != Clean {f.clean_written} + Removed {f.removed_written}")
        if f.removed != f.removed_written:
            problems.append(
                f"File {f.name}: dòng bị loại theo phân loại ({f.removed}) "
                f"khác file Removed ({f.removed_written})")
    for m in stats.months:
        if m.raw != m.clean_written + m.removed_written:
            problems.append(
                f"Tháng {m.month}: Raw {m.raw} != Clean {m.clean_written} + Removed {m.removed_written}")
        if m.removed != m.removed_written:
            problems.append(
                f"Tháng {m.month}: dòng bị loại theo phân loại ({m.removed}) "
                f"khác file Removed ({m.removed_written})")
    if stats.raw_total != stats.clean_total + stats.removed_total:
        problems.append(
            f"Tổng: Raw {stats.raw_total} != Clean {stats.clean_total} + Removed {stats.removed_total}")
    return problems


def build_warnings(stats: RunStats) -> pd.DataFrame:
    rows: list[tuple[str, str, str, int]] = []
    for f in stats.files:
        if f.raw == 0:
            rows.append(("File không có dòng dữ liệu", f.name, "Chỉ có tiêu đề", 0))
        if f.months > 1:
            rows.append(("File có nhiều tháng", f.name,
                         f"Dữ liệu thuộc {f.months} tháng. Thông tin, không phải lỗi", f.months))
        if f.blank_time_of_fetch:
            rows.append(("Time of Fetch trống", f.name,
                         "Dòng không có thời gian fetch. Không thuộc rule nên vẫn giữ nguyên",
                         f.blank_time_of_fetch))
        if f.invalid_time_of_fetch:
            rows.append(("Time of Fetch sai định dạng", f.name,
                         "Giá trị không đúng yy-Mon-dd HHMM. Không thuộc rule nên vẫn giữ nguyên",
                         f.invalid_time_of_fetch))
    for file_name, value, count in stats.unknown_move_kinds:
        rows.append(("Move Kind chưa biết", file_name,
                     f"Giá trị '{value}' không nằm trong danh sách đã biết. Không bị loại theo rule",
                     count))
    if stats.duplicate_rows:
        rows.append(("Dòng trùng khóa", "(tất cả file)",
                     "Trùng Unit Nbr, Move Kind, From, To, Time Completed. Không tự xóa theo quy định",
                     stats.duplicate_rows))
    return pd.DataFrame(rows, columns=["Loại cảnh báo", "File", "Chi tiết", "Số dòng"])


def _autofit(ws, df: pd.DataFrame) -> None:
    for idx, col in enumerate(df.columns, start=1):
        values = [str(col)] + [str(v) for v in df[col].tolist()]
        ws.column_dimensions[get_column_letter(idx)].width = min(max(len(v) for v in values) + 2, 70)


def write_excel(stats: RunStats, problems: Sequence[str], path: Path) -> None:
    rate = f"{stats.removed_total / stats.raw_total:.2%}" if stats.raw_total else "0%"
    overview = pd.DataFrame(
        [
            ("Run ID", stats.run_id),
            ("Thời điểm chạy", stats.run_at),
            ("Số file đầu vào", len(stats.files)),
            ("Số tháng (theo Time Completed)", len(stats.months)),
            ("Tổng dòng đầu vào (Raw)", stats.raw_total),
            ("Dòng hợp lệ (CLEAN_DATA)", stats.clean_total),
            ("Dòng bị loại (REMOVED_DATA)", stats.removed_total),
            ("Tỷ lệ bị loại", rate),
            ("Trạng thái đối soát", "OK" if not problems else "LỖI"),
        ],
        columns=["Chỉ số", "Giá trị"],
    )
    by_file = pd.DataFrame([
        {
            "File": f.name,
            "Dòng đầu vào": f.raw,
            "Clean": f.clean_written,
            "Removed": f.removed_written,
            "Raw = Clean + Removed": "OK" if f.raw == f.clean_written + f.removed_written else "LỖI",
        }
        for f in stats.files
    ])
    by_month = pd.DataFrame([
        {
            "Tháng": m.month,
            "Dòng đầu vào": m.raw,
            "Clean": m.clean_written,
            "Removed": m.removed_written,
            "Raw = Clean + Removed": "OK" if m.raw == m.clean_written + m.removed_written else "LỖI",
        }
        for m in stats.months
    ])
    by_rule_rows = []
    for r in stats.rules:
        row = {
            "Rule_ID": r.rule_id,
            "Mô tả": r.description,
            "Tổng lượt vi phạm": sum(f.rule_hits.get(r.rule_id, 0) for f in stats.files),
        }
        for f in stats.files:
            row[f.name] = f.rule_hits.get(r.rule_id, 0)
        by_rule_rows.append(row)
    overlap = pd.DataFrame(
        [{"Số rule vi phạm": n, "Số dòng": c} for n, c in sorted(stats.overlap.items())],
        columns=["Số rule vi phạm", "Số dòng"],
    )
    reconciliation = pd.DataFrame(
        {"Kết quả": list(problems) if problems else ["Raw = Clean + Removed cho mọi file và tháng"]}
    )

    sheets = {
        "Overview": overview,
        "By_File": by_file,
        "By_Month": by_month,
        "By_Rule": pd.DataFrame(by_rule_rows),
        "Rule_Overlap": overlap,
        "Warnings": build_warnings(stats),
        "Reconciliation": reconciliation,
    }
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            _autofit(writer.sheets[name], df)
