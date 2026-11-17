"""Kiểm chứng bộ rule Python (cleaning/reference.py) với bảng case. Chạy thuần Python, không cần DuckDB."""
from __future__ import annotations

import pytest

from cleaning.reference import parse_report_month, rule_ids
from rule_cases import CASES


@pytest.mark.parametrize("case_id,move,fetch,put,expected", CASES, ids=[c[0] for c in CASES])
def test_reference_rules_match_case_table(case_id, move, fetch, put, expected):
    assert set(rule_ids(move, fetch, put)) == expected, case_id


@pytest.mark.parametrize("value,month", [
    ("26-Aug-14 2359", "2026-08"),
    ("26-Oct-31 0000", "2026-10"),
    ("26-Feb-28 1200", "2026-02"),
    ("  26-Sep-02 0005  ", "2026-09"),   # khoảng trắng hai đầu được bỏ
    ("26-aug-14 2359", "2026-08"),       # không phân biệt hoa thường
])
def test_valid_time_completed(value, month):
    assert parse_report_month(value) == month


@pytest.mark.parametrize("value", [
    "2026-08-14 2359",   # sai thứ tự
    "26-Feb-30 1200",    # ngày không tồn tại
    "26-Xyz-14 1200",    # tháng sai
    "26-Aug-14 2460",    # giờ sai
    "26-Aug-14 236",     # thiếu chữ số
    "",
    None,
])
def test_invalid_time_completed(value):
    assert parse_report_month(value) is None


def test_r06_uses_only_discharge_and_receival():
    assert rule_ids("Recieve", "RTG01", None) == []
    assert rule_ids("Receive", "RTG01", None) == []
    assert rule_ids("Receival", "RTG01", None) == ["R06"]
    assert rule_ids("Discharge", "RTG01", None) == ["R06"]
