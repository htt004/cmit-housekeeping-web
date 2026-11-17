"""Test từng rule trên engine DuckDB. Bỏ qua nếu chưa cài duckdb."""
from __future__ import annotations

import pytest

pytest.importorskip("duckdb", reason="Cần cài duckdb để chạy test engine")

from conftest import make_row  # noqa: E402
from rule_cases import CASES  # noqa: E402


def test_rule_outcomes_for_every_case(tmp_path, make_csv, run_engine, read_out):
    rows = [
        make_row(f"U{i:03d}", move, fetch, put)
        for i, (_, move, fetch, put, _) in enumerate(CASES)
    ]
    src = make_csv(tmp_path / "any_name.csv", rows)

    result = run_engine([src], tmp_path / "out")
    _, clean = read_out(result.clean_path)
    _, removed = read_out(result.removed_path)

    clean_units = {r["Unit Nbr"] for r in clean}
    removed_map = {r["Unit Nbr"]: r["Rule_ID"] for r in removed}

    for i, (case_id, _, _, _, expected) in enumerate(CASES):
        unit = f"U{i:03d}"
        if expected:
            assert removed_map.get(unit) == "|".join(sorted(expected)), case_id
            assert unit not in clean_units, case_id
        else:
            assert unit in clean_units, case_id
            assert unit not in removed_map, case_id

    assert len(clean) + len(removed) == len(CASES)


def test_multi_rule_row_removed_only_once(tmp_path, make_csv, run_engine, read_out):
    src = make_csv(tmp_path / "x.csv", [make_row("U1", "Load", None, None)])
    result = run_engine([src], tmp_path / "out")
    _, removed = read_out(result.removed_path)
    _, clean = read_out(result.clean_path)
    assert len(removed) == 1
    assert clean == []
    assert removed[0]["Rule_ID"] == "R02|R03"
    assert "R02:" in removed[0]["Removal_Reason"]
    assert "R03:" in removed[0]["Removal_Reason"]


def test_original_values_are_kept_unchanged(tmp_path, make_csv, run_engine, read_out):
    src = make_csv(tmp_path / "x.csv", [make_row("U1", "Yard Move", "  QC01  ", None)])
    result = run_engine([src], tmp_path / "out")
    _, removed = read_out(result.removed_path)
    assert removed[0]["Rule_ID"] == "R05"
    assert removed[0]["Fetch CHE Name"] == "  QC01  "
    assert removed[0]["Source_File"] == "x.csv"


def test_exact_duplicates_are_not_removed(tmp_path, make_csv, run_engine, read_out):
    row = make_row("DUP", "Yard Move", "QC01", "QC02")
    src = make_csv(tmp_path / "x.csv", [row, dict(row)])
    result = run_engine([src], tmp_path / "out")
    _, clean = read_out(result.clean_path)
    assert len(clean) == 2
    assert result.stats.duplicate_rows == 1
