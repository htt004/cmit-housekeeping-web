"""Kiểm thử hiệu năng và giới hạn tài nguyên với dữ liệu tổng hợp 1–5 triệu dòng.

Chạy khi đặt CMIT_SCALE_ROWS, ví dụ 1000000 hoặc 5000000. Tùy chọn:
  CMIT_MEMORY_LIMIT  giới hạn bộ nhớ DuckDB (mặc định 1GB cho test này)
  CMIT_SCALE_FILES   số file chia nhỏ (mặc định: mỗi file tối đa 2 triệu dòng)

Kết quả đo (thời gian từng bước, số dòng/giây) được ghi vào scale_report.json trong thư mục tạm
và in ra khi chạy pytest -s.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("duckdb", reason="Cần cài duckdb để chạy test scale")

from cleaning.engine import CleaningEngine, EngineSettings  # noqa: E402
from cleaning.synthetic import SyntheticSpec, generate  # noqa: E402

SCALE_ROWS = int(os.environ.get("CMIT_SCALE_ROWS", "0") or 0)


@pytest.mark.skipif(SCALE_ROWS <= 0, reason="Đặt CMIT_SCALE_ROWS (ví dụ 1000000) để chạy test scale")
def test_scale_run_matches_reference_and_respects_memory_limit(tmp_path, capsys):
    files = int(os.environ.get("CMIT_SCALE_FILES", "0") or 0) or max(1, -(-SCALE_ROWS // 2_000_000))
    memory_limit = os.environ.get("CMIT_MEMORY_LIMIT", "1GB")

    t0 = time.perf_counter()
    expected = generate(tmp_path / "in", SyntheticSpec(rows=SCALE_ROWS, files=files))
    gen_seconds = time.perf_counter() - t0

    temp_root = tmp_path / "duck_tmp"
    settings = EngineSettings(memory_limit=memory_limit, temp_directory=temp_root)
    inputs = sorted((tmp_path / "in").glob("*.csv"))

    t1 = time.perf_counter()
    result = CleaningEngine(settings=settings).run(inputs, tmp_path / "out")
    run_seconds = time.perf_counter() - t1

    # Đối chiếu với số tham chiếu của bộ sinh dữ liệu
    assert result.stats.raw_total == SCALE_ROWS
    assert result.stats.raw_total == result.stats.clean_total + result.stats.removed_total
    by_month = {m.month: m for m in result.stats.months}
    assert set(by_month) == set(expected["months"])
    for month, counts in expected["months"].items():
        m = by_month[month]
        assert (m.raw, m.removed_written, m.clean_written) == (counts["raw"], counts["removed"], counts["clean"]), month
    by_file = {f.name: f for f in result.stats.files}
    for name, counts in expected["files"].items():
        f = by_file[name]
        assert (f.raw, f.removed_written, f.clean_written) == (counts["raw"], counts["removed"], counts["clean"]), name

    # Thư mục temp của DuckDB phải được dọn sau khi chạy
    assert not (temp_root / result.run_id).exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "SUCCESS"
    report = {
        "rows": SCALE_ROWS,
        "files": files,
        "memory_limit": memory_limit,
        "generate_seconds": round(gen_seconds, 2),
        "run_seconds": round(run_seconds, 2),
        "rows_per_second": round(SCALE_ROWS / run_seconds) if run_seconds else None,
        "timings_seconds": manifest["timings_seconds"],
    }
    (tmp_path / "scale_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nSCALE REPORT:", json.dumps(report, ensure_ascii=False))
