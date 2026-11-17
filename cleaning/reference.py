"""Triển khai Python độc lập của 8 rule và của cách lấy tháng từ Time Completed.

Dùng để KIỂM CHỨNG engine DuckDB (đối chiếu số đếm) và để sinh dữ liệu tổng hợp có số tham chiếu.
Không dùng trong luồng sản xuất. Logic phải khớp với cleaning/rules.py.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from .config import COL_FETCH, COL_MOVE, COL_PUT, COL_TIME_COMPLETED
from .ingest import map_columns
from .rules import MONTHS

_TIME = re.compile(r"^([0-9]{2})-([A-Za-z]{3})-([0-9]{2}) ([01][0-9]|2[0-3])[0-5][0-9]$")
_MONTH_NUM = {m.upper(): i for i, m in enumerate(MONTHS, 1)}


def _trim(value: Optional[str]) -> str:
    # Giống TRIM trong SQL: chỉ bỏ dấu cách ở hai đầu
    return (value or "").strip(" ")


def _norm(value: Optional[str]) -> str:
    # Giống norm() trong rules.py: gộp mọi khoảng trắng, bỏ đầu/cuối, viết hoa
    return " ".join((value or "").split()).upper()


def parse_report_month(value: Optional[str]) -> Optional[str]:
    """'YYYY-MM' từ Time Completed (yy-Mon-dd HHMM), hoặc None nếu sai định dạng/không phải ngày."""
    t = _trim(value)
    m = _TIME.match(t)
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2).upper(), m.group(3)
    if mon not in _MONTH_NUM:
        return None
    try:
        d = date(2000 + int(yy), _MONTH_NUM[mon], int(dd))
    except ValueError:
        return None
    return f"{d.year:04d}-{d.month:02d}"


def rule_ids(move: Optional[str], fetch: Optional[str], put: Optional[str]) -> list[str]:
    """Danh sách rule vi phạm, đúng thứ tự R01..R08."""
    mk, f, p = _norm(move), _norm(fetch), _norm(put)
    fb, pb = f == "", p == ""
    ids: list[str] = []
    if mk in ("OTHER", "SHIFT O.B."):
        ids.append("R01")
    if fb and mk in ("LOAD", "DELIVERY"):
        ids.append("R02")
    if fb and pb:
        ids.append("R03")
    if f in ("RTG16", "RTG17"):
        ids.append("R04")
    if f[:2] == "QC" and pb:
        ids.append("R05")
    if pb and mk in ("DISCHARGE", "RECEIVAL"):
        ids.append("R06")
    if p in ("RTG16", "RTG17"):
        ids.append("R07")
    if p[:2] == "QC" and fb:
        ids.append("R08")
    return ids


def classify_row(row: dict) -> tuple[Optional[str], list[str]]:
    """(tháng, rule vi phạm) của một dòng. Tháng None nghĩa là sai định dạng Time Completed."""
    month = parse_report_month(row.get(COL_TIME_COMPLETED))
    return month, rule_ids(row.get(COL_MOVE), row.get(COL_FETCH), row.get(COL_PUT))


def reference_counts(paths: Iterable[Path]) -> dict:
    """Đếm tham chiếu theo file và theo tháng, đọc bằng csv chuẩn của Python.

    Trả về: {"files": {tên: {raw, removed, clean}}, "months": {YYYY-MM: {raw, removed, clean}},
             "invalid": {tên: số dòng sai Time Completed}}
    """
    per_file: dict[str, dict] = {}
    per_month: dict[str, Counter] = defaultdict(Counter)
    invalid: Counter = Counter()

    for path in paths:
        p = Path(path)
        with p.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            positions = {canon: idx for canon, idx, _ in map_columns(header)}
            fc: Counter = Counter()
            for row in reader:
                if not row:
                    continue
                values = {c: (row[i] if i < len(row) else "") for c, i in positions.items()}
                month, ids = classify_row(values)
                if month is None:
                    invalid[p.name] += 1
                    continue
                key = "removed" if ids else "clean"
                fc["raw"] += 1
                fc[key] += 1
                per_month[month]["raw"] += 1
                per_month[month][key] += 1
            per_file[p.name] = dict(fc)

    return {
        "files": per_file,
        "months": {m: dict(c) for m, c in sorted(per_month.items())},
        "invalid": dict(invalid),
    }
