"""Integration test trên file RAW thật, không phụ thuộc tên file.

Chạy khi đặt CMIT_TEST_DATA_DIR. Test sẽ:
- quét mọi file .csv trong thư mục (bất kể tên),
- sao chép sang thư mục tạm với tên ngẫu nhiên để chắc chắn engine không dựa vào tên,
- xác nhận số theo tháng (lấy từ Time Completed) khớp với số đã review,
- xác nhận RAW gốc không thay đổi.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

pytest.importorskip("duckdb", reason="Cần cài duckdb để chạy integration test")

from cleaning.engine import CleaningEngine  # noqa: E402

DATA_DIR = os.environ.get("CMIT_TEST_DATA_DIR")

# Số tham chiếu đã được review: tháng -> (raw, removed, clean)
REFERENCE_BY_MONTH = {
    "2026-08": (132_997, 6_853, 126_144),
    "2026-09": (138_675, 8_541, 130_134),
    "2026-10": (144_247, 8_621, 135_626),
}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.mark.skipif(not DATA_DIR, reason="Đặt CMIT_TEST_DATA_DIR để chạy test tích hợp")
def test_real_files_match_reviewed_numbers_by_month(tmp_path):
    originals = sorted(p for p in Path(DATA_DIR).iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    assert originals, "Không có file CSV nào trong thư mục"
    before = {p.name: _sha(p) for p in originals}

    # Tên ngẫu nhiên, không liên quan đến tháng
    staged_dir = tmp_path / "staged"
    staged_dir.mkdir()
    staged = []
    for p in originals:
        dest = staged_dir / f"batch_{uuid.uuid4().hex[:10]}.csv"
        shutil.copyfile(p, dest)
        staged.append(dest)

    result = CleaningEngine().run(staged, tmp_path / "out")

    by_month = {m.month: m for m in result.stats.months}
    assert set(by_month) == set(REFERENCE_BY_MONTH)
    for month, (raw, removed, clean) in REFERENCE_BY_MONTH.items():
        m = by_month[month]
        assert (m.raw, m.removed_written, m.clean_written) == (raw, removed, clean), month

    assert result.stats.raw_total == 415_919
    assert result.stats.removed_total == 24_015
    assert result.stats.clean_total == 391_904

    # RAW gốc không thay đổi
    assert {p.name: _sha(p) for p in originals} == before
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "SUCCESS"
    assert all(e["sha256_before"] == e["sha256_after"] for e in manifest["inputs"])
