"""Định nghĩa 8 rule loại dòng và các biểu thức SQL dùng chung.

Chuẩn hóa chỉ dùng khi so sánh: NULL và chuỗi khoảng trắng là "trống",
không phân biệt hoa thường, gộp khoảng trắng. Giá trị đầu ra không bị đổi.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import COL_FETCH, COL_MOVE, COL_PUT, COL_TIME_COMPLETED, COL_TIME_FETCH

MONTHS: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

# Định dạng Time Completed/Time of Fetch trong RAW: yy-Mon-dd HHMM, ví dụ 26-Oct-31 2358
TIME_PATTERN = r"^[0-9]{2}-[A-Za-z]{3}-[0-9]{2} ([01][0-9]|2[0-3])[0-5][0-9]$"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def norm(column: str) -> str:
    """Giá trị đã chuẩn hóa: NULL -> '', gộp khoảng trắng (kể cả tab), bỏ đầu/cuối, viết hoa."""
    return (
        "UPPER(TRIM(REGEXP_REPLACE(COALESCE("
        + quote_ident(column)
        + ", ''), '\\s+', ' ', 'g')))"
    )


def _trimmed(column: str) -> str:
    return f"TRIM(COALESCE({quote_ident(column)}, ''))"


def report_month_expr(column: str = COL_TIME_COMPLETED) -> str:
    """Biểu thức SQL trả về 'YYYY-MM' từ Time Completed, hoặc NULL nếu sai định dạng/không phải ngày.

    Năm là 2 chữ số đầu, tháng là 3 chữ cái, ngày là 2 chữ số sau (yy-Mon-dd).
    """
    t = _trimmed(column)
    month_case = (
        "CASE UPPER(SUBSTR(" + t + ", 4, 3)) "
        + " ".join(f"WHEN '{m.upper()}' THEN '{i:02d}'" for i, m in enumerate(MONTHS, 1))
        + " END"
    )
    iso_date = (
        "'20' || SUBSTR(" + t + ", 1, 2) || '-' || " + month_case
        + " || '-' || SUBSTR(" + t + ", 8, 2)"
    )
    return (
        "CASE WHEN REGEXP_MATCHES(" + t + ", " + sql_str(TIME_PATTERN) + ") "
        "THEN STRFTIME(TRY_CAST(" + iso_date + " AS DATE), '%Y-%m') END"
    )


def time_fetch_invalid_sql() -> str:
    """Điều kiện: Time of Fetch có giá trị nhưng sai định dạng (chỉ cảnh báo)."""
    t = _trimmed(COL_TIME_FETCH)
    return f"({t} <> '' AND NOT REGEXP_MATCHES({t}, {sql_str(TIME_PATTERN)}))"


_MOVE = norm(COL_MOVE)
_FETCH = norm(COL_FETCH)
_PUT = norm(COL_PUT)

_FETCH_BLANK = f"({_FETCH} = '')"
_PUT_BLANK = f"({_PUT} = '')"
_FETCH_QC = f"(LEFT({_FETCH}, 2) = 'QC')"
_PUT_QC = f"(LEFT({_PUT}, 2) = 'QC')"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    condition: str  # biểu thức SQL boolean


RULES: tuple[Rule, ...] = (
    Rule(
        "R01",
        "Move Kind là Other hoặc Shift O.B.",
        f"{_MOVE} IN ('OTHER', 'SHIFT O.B.')",
    ),
    Rule(
        "R02",
        "Fetch CHE Name trống và Move Kind là Load hoặc Delivery",
        f"{_FETCH_BLANK} AND {_MOVE} IN ('LOAD', 'DELIVERY')",
    ),
    Rule(
        "R03",
        "Fetch CHE Name và Put CHE Name cùng trống",
        f"{_FETCH_BLANK} AND {_PUT_BLANK}",
    ),
    Rule(
        "R04",
        "Fetch CHE Name là RTG16 hoặc RTG17",
        f"{_FETCH} IN ('RTG16', 'RTG17')",
    ),
    Rule(
        "R05",
        "Fetch CHE Name bắt đầu bằng QC và Put CHE Name trống",
        f"{_FETCH_QC} AND {_PUT_BLANK}",
    ),
    Rule(
        "R06",
        "Put CHE Name trống và Move Kind là Discharge hoặc Receival",
        f"{_PUT_BLANK} AND {_MOVE} IN ('DISCHARGE', 'RECEIVAL')",
    ),
    Rule(
        "R07",
        "Put CHE Name là RTG16 hoặc RTG17",
        f"{_PUT} IN ('RTG16', 'RTG17')",
    ),
    Rule(
        "R08",
        "Put CHE Name bắt đầu bằng QC và Fetch CHE Name trống",
        f"{_PUT_QC} AND {_FETCH_BLANK}",
    ),
)


def _validate(rules: Iterable[Rule]) -> None:
    ids = [r.rule_id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Trùng Rule_ID: {ids}")


_validate(RULES)


def flag_column(rule_id: str) -> str:
    return f"flag_{rule_id}"


def any_flag_sql(rules: Iterable[Rule]) -> str:
    return " OR ".join(quote_ident(flag_column(r.rule_id)) for r in rules) or "FALSE"
