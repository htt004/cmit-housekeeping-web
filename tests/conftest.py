"""Fixture và helper dùng chung. Không import DuckDB ở mức module để test thuần Python vẫn chạy được."""
from __future__ import annotations

import codecs
import csv
import io
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import pytest

from cleaning.config import EXPECTED_COLUMNS

# Time Completed "26-Aug-14 2359" nghĩa là 2026-08-14 23:59 (yy-Mon-dd HHMM)
BASE_ROW: dict[str, Any] = {
    "Unit Nbr": "U000",
    "Move Kind": "Yard Move",
    "From Position": "Y-CMIT-1A01A.1",
    "To Position": "Y-CMIT-1A01B.1",
    "Crane CHE Name": "",
    "Fetch CHE Name": "",
    "Put CHE Name": "",
    "Time Completed": "26-Aug-14 2359",
    "Time of Fetch": "26-Aug-14 2351",
    "Unit Category": "Export",
    "Line Op": "MAE",
    "Unit POD": "VNBDG",
    "Unit Frght Kind": "FCL",
}


def make_row(unit: str, move: Optional[str], fetch: Optional[str], put: Optional[str], **extra: Any) -> dict:
    row = dict(BASE_ROW)
    row.update({"Unit Nbr": unit, "Move Kind": move, "Fetch CHE Name": fetch, "Put CHE Name": put})
    row.update(extra)
    return row


def _canonical_for(header: str) -> str:
    key = " ".join(header.split()).casefold()
    for c in EXPECTED_COLUMNS:
        if c.casefold() == key:
            return c
    return header


def write_csv(
    path: Path,
    rows: Iterable[dict],
    *,
    encoding: str = "utf-8",
    bom: bool = False,
    columns: tuple[str, ...] = EXPECTED_COLUMNS,
) -> Path:
    """Ghi CSV với CRLF. `columns` là header thực tế (có thể khác chuẩn để test chuẩn hóa)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(columns)
    for r in rows:
        values = []
        for c in columns:
            key = c if c in r else _canonical_for(c)
            v = r.get(key)
            values.append("" if v is None else v)
        writer.writerow(values)
    data = buf.getvalue().encode(encoding)
    if bom and encoding.lower().startswith("utf-8"):
        data = codecs.BOM_UTF8 + data
    path.write_bytes(data)
    return path


def read_parquet_rows(path: Path) -> tuple[list[str], list[dict]]:
    import duckdb  # import muộn: chỉ cần khi test DuckDB

    con = duckdb.connect(":memory:")
    try:
        cur = con.execute(f"SELECT * FROM read_parquet({_sql_lit(path.as_posix())})")
        cols = [d[0] for d in cur.description]
        return cols, [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@pytest.fixture
def make_csv() -> Callable[..., Path]:
    return write_csv


@pytest.fixture
def run_engine() -> Callable[..., Any]:
    from cleaning.engine import CleaningEngine

    def _run(inputs, out_base, **kwargs):
        return CleaningEngine(**kwargs).run(inputs, out_base)

    return _run


@pytest.fixture
def read_out() -> Callable[[Path], tuple[list[str], list[dict]]]:
    return read_parquet_rows
