"""Đối chiếu bộ rule Python với 3 file RAW thật. Chạy khi đặt CMIT_TEST_DATA_DIR.

Không phụ thuộc tên file: quét mọi file .csv trong thư mục, tháng lấy từ Time Completed.
Chạy thuần Python, không cần DuckDB.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from cleaning.reference import reference_counts

DATA_DIR = os.environ.get("CMIT_TEST_DATA_DIR")

# Số tham chiếu đã được review: tháng -> (raw, removed, clean)
REFERENCE_BY_MONTH = {
    "2026-08": (132_997, 6_853, 126_144),
    "2026-09": (138_675, 8_541, 130_134),
    "2026-10": (144_247, 8_621, 135_626),
}


@pytest.mark.skipif(not DATA_DIR, reason="Đặt CMIT_TEST_DATA_DIR để chạy")
def test_reference_reproduces_reviewed_numbers_for_real_files():
    csv_files = sorted(p for p in Path(DATA_DIR).iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    assert csv_files, "Không có file CSV nào trong thư mục"

    result = reference_counts(csv_files)

    assert not result["invalid"], result["invalid"]
    assert set(result["months"]) == set(REFERENCE_BY_MONTH)
    for month, (raw, removed, clean) in REFERENCE_BY_MONTH.items():
        got = result["months"][month]
        assert (got["raw"], got["removed"], got["clean"]) == (raw, removed, clean), month

    total_raw = sum(v["raw"] for v in result["months"].values())
    assert total_raw == 415_919
