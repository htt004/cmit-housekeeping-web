"""Kiểm chứng bộ sinh dữ liệu tổng hợp và số tham chiếu của nó. Thuần Python."""
from __future__ import annotations

from cleaning.reference import reference_counts
from cleaning.synthetic import SyntheticSpec, generate


def test_generator_bookkeeping_matches_rescan_of_written_files(tmp_path):
    spec = SyntheticSpec(rows=3_000, files=3, seed=7)
    expected = generate(tmp_path / "in", spec)

    files = sorted((tmp_path / "in").glob("*.csv"))
    rescanned = reference_counts(files)

    assert expected["total"]["raw"] == 3_000
    assert expected["total"]["raw"] == expected["total"]["clean"] + expected["total"]["removed"]
    assert {k: v for k, v in expected["files"].items()} == rescanned["files"]
    assert expected["months"] == rescanned["months"]
    assert not rescanned["invalid"]


def test_generator_is_deterministic_for_same_seed(tmp_path):
    a = generate(tmp_path / "a", SyntheticSpec(rows=500, seed=1))
    b = generate(tmp_path / "b", SyntheticSpec(rows=500, seed=1))
    assert a == b
    assert (tmp_path / "a" / "synthetic_01.csv").read_bytes() == (tmp_path / "b" / "synthetic_01.csv").read_bytes()


def test_generator_spreads_rows_over_months_from_time_completed(tmp_path):
    expected = generate(tmp_path / "in", SyntheticSpec(rows=1_500, files=1, seed=3))
    assert set(expected["months"]) == {"2026-08", "2026-09", "2026-10"}
