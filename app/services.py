"""Lớp dịch vụ cho giao diện Streamlit. Không import Streamlit. Không import DuckDB ở mức module.

Quy ước thư mục workspace:
  workspace/uploads/<batch_id>/   file CSV đã tải lên, đặt quyền chỉ đọc
  workspace/outputs/<run_id>/     kết quả từng lần chạy (do engine tạo)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pandas as pd

from cleaning.config import (
    ALLOWED_EXTENSIONS,
    CLEAN_FILE_NAME,
    ENV_WORKSPACE,
    MANIFEST_FILE_NAME,
    REMOVED_FILE_NAME,
    SUMMARY_FILE_NAME,
)
from cleaning.errors import InputError


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    def ensure(self) -> "Workspace":
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        return self


def workspace_from_env(default: Optional[Path] = None) -> Workspace:
    root = os.environ.get(ENV_WORKSPACE)
    base = Path(root) if root else (default or Path.cwd() / "workspace")
    return Workspace(base.resolve()).ensure()


def user_workspace(base: Workspace, user: str) -> Workspace:
    """Workspace riêng cho từng người dùng: base/users/<hash>/. Người khác không liệt kê được.

    Thư mục đặt theo hash của định danh, không dùng trực tiếp chuỗi người dùng làm tên thư mục.
    File owner.txt ghi định danh gốc để tra cứu khi kiểm toán.
    """
    key = hashlib.sha256(user.strip().lower().encode("utf-8")).hexdigest()[:24]
    ws = Workspace(base.root / "users" / key).ensure()
    owner = ws.root / "owner.txt"
    if not owner.exists():
        owner.write_text(user.strip().lower() + "\n", encoding="utf-8")
    return ws


def new_session_id() -> str:
    """Mã phiên ngẫu nhiên (32 ký tự hex). Dùng làm tên thư mục, không đoán được."""
    return uuid.uuid4().hex


def session_workspace(base: Workspace, session_id: str) -> Workspace:
    """Workspace riêng cho một phiên trình duyệt: base/sessions/<session_id>/."""
    if len(session_id) != 32 or any(c not in "0123456789abcdef" for c in session_id):
        raise InputError("Mã phiên không hợp lệ.")
    return Workspace(base.root / "sessions" / session_id).ensure()


def delete_workspace(ws: Workspace) -> None:
    """Xóa toàn bộ workspace của phiên, kể cả file chỉ đọc. Chỉ xóa trong thư mục sessions."""
    if ws.root.parent.name != "sessions":
        raise InputError("Từ chối xóa: không phải workspace của phiên.")

    def _clear(func, path, _exc_info) -> None:
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(ws.root, onerror=_clear, ignore_errors=True)


def new_batch_id() -> str:
    return uuid.uuid4().hex[:12]


def batch_dir(ws: Workspace, batch_id: str) -> Path:
    return ws.uploads / batch_id


def save_uploads(uploads: Sequence, batch_id: str, ws: Workspace) -> list[Path]:
    """Lưu file tải lên vào thư mục batch. Chỉ nhận .csv, không ghi đè, đặt quyền chỉ đọc.

    `uploads` là các đối tượng có thuộc tính `name` và phương thức `getbuffer()` hoặc `read()`
    (đúng với UploadedFile của Streamlit).
    """
    target = batch_dir(ws, batch_id)
    target.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    errors: list[str] = []
    seen: set[str] = set()
    for up in uploads:
        name = Path(up.name).name  # bỏ mọi phần đường dẫn người dùng gửi kèm
        if not name:
            errors.append("Tên file rỗng")
            continue
        if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
            errors.append(f"Không phải file CSV: {name}")
            continue
        if name in seen or (target / name).exists():
            errors.append(f"Trùng tên trong batch: {name}")
            continue
        seen.add(name)
        data = bytes(up.getbuffer()) if hasattr(up, "getbuffer") else up.read()
        dest = target / name
        dest.write_bytes(data)
        try:
            os.chmod(dest, 0o444)
        except OSError:
            pass  # Windows có thể bỏ qua một phần quyền
        saved.append(dest)
    if errors:
        raise InputError("Một số file không được lưu:\n - " + "\n - ".join(errors))
    return saved


def list_batch_files(ws: Workspace, batch_id: str) -> list[Path]:
    d = batch_dir(ws, batch_id)
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS)


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    run_dir: Path
    status: str
    started_at: str
    raw_total: Optional[int]
    clean_total: Optional[int]
    removed_total: Optional[int]
    error: Optional[str]


def read_manifest(run_dir: Path) -> dict:
    path = run_dir / MANIFEST_FILE_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs(ws: Workspace) -> list[RunInfo]:
    """Danh sách các lần chạy, mới nhất trước."""
    runs: list[RunInfo] = []
    if not ws.outputs.exists():
        return runs
    for d in ws.outputs.iterdir():
        if not (d.is_dir() and (d / MANIFEST_FILE_NAME).exists()):
            continue
        m = read_manifest(d)
        counts = m.get("counts") or {}
        runs.append(RunInfo(
            run_id=m.get("run_id", d.name),
            run_dir=d,
            status=m.get("status", "?"),
            started_at=m.get("started_at", ""),
            raw_total=counts.get("raw_total"),
            clean_total=counts.get("clean_total"),
            removed_total=counts.get("removed_total"),
            error=m.get("error"),
        ))
    return sorted(runs, key=lambda r: r.started_at, reverse=True)


def read_summary_sheets(run_dir: Path) -> dict[str, pd.DataFrame]:
    return pd.read_excel(run_dir / SUMMARY_FILE_NAME, sheet_name=None, engine="openpyxl")


def output_path(run_dir: Path, dataset: str) -> Path:
    names = {
        "clean": CLEAN_FILE_NAME,
        "removed": REMOVED_FILE_NAME,
        "summary": SUMMARY_FILE_NAME,
        "manifest": MANIFEST_FILE_NAME,
    }
    if dataset not in names:
        raise ValueError(f"Không biết tập dữ liệu: {dataset}")
    return run_dir / names[dataset]


def preview(
    run_dir: Path,
    dataset: str,
    months: Optional[Iterable[str]] = None,
    rule_ids: Optional[Iterable[str]] = None,
    limit: int = 200,
) -> tuple[pd.DataFrame, int]:
    """Xem trước dữ liệu từ file Parquet. Trả về (tối đa `limit` dòng, tổng số dòng khớp bộ lọc).

    Lọc bằng tham số (không ghép chuỗi người dùng vào SQL). Chỉ dùng DuckDB khi gọi hàm này.
    """
    import duckdb  # import muộn: trang khác không cần DuckDB

    if dataset not in ("clean", "removed"):
        raise ValueError("dataset phải là 'clean' hoặc 'removed'")
    path = output_path(run_dir, dataset)
    where, params = [], []
    month_list = [m for m in (months or []) if m]
    if month_list:
        where.append('"Report_Month" IN (' + ", ".join("?" for _ in month_list) + ")")
        params.extend(month_list)
    rule_list = [r for r in (rule_ids or []) if r]
    if rule_list and dataset == "removed":
        where.append("(" + " OR ".join('"Rule_ID" LIKE ?' for _ in rule_list) + ")")
        params.extend(f"%{r}%" for r in rule_list)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    literal_path = "'" + path.as_posix().replace("'", "''") + "'"
    source = f"read_parquet({literal_path})"
    con = duckdb.connect(":memory:")
    try:
        total = con.execute(f"SELECT COUNT(*) FROM {source}{clause}", params).fetchone()[0]
        df = con.execute(f"SELECT * FROM {source}{clause} LIMIT {int(limit)}", params).fetchdf()
    finally:
        con.close()
    return df, int(total)


def file_bytes(path: Path) -> bytes:
    return path.read_bytes()
