"""Test luồng chính trên DuckDB: Run ID, cấu trúc đầu ra, tháng, đối soát, manifest, RAW, giới hạn tài nguyên."""
from __future__ import annotations

import hashlib
import json

import pytest

pytest.importorskip("duckdb", reason="Cần cài duckdb để chạy test engine")
openpyxl = pytest.importorskip("openpyxl")

from cleaning.config import (  # noqa: E402
    CLEAN_FILE_NAME,
    EXPECTED_COLUMNS,
    MANIFEST_FILE_NAME,
    REMOVED_FILE_NAME,
    SUMMARY_FILE_NAME,
)
from cleaning.engine import CleaningEngine, EngineSettings, precheck  # noqa: E402
from cleaning.errors import DataFormatError, InputError, RunFolderError  # noqa: E402
from conftest import make_row  # noqa: E402


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_each_run_gets_its_own_folder_and_run_id(tmp_path, make_csv, run_engine):
    src = make_csv(tmp_path / "in.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    r1 = run_engine([src], tmp_path / "out")
    r2 = run_engine([src], tmp_path / "out")

    assert r1.run_id != r2.run_id
    assert r1.run_dir != r2.run_dir
    assert r1.run_dir.parent == tmp_path / "out" == r2.run_dir.parent
    assert r1.run_id.startswith("RUN_")
    assert (r1.run_dir / CLEAN_FILE_NAME).exists()
    assert (r2.run_dir / CLEAN_FILE_NAME).exists()


def test_existing_run_folder_is_never_overwritten(tmp_path, make_csv, run_engine):
    src = make_csv(tmp_path / "in.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    first = run_engine([src], tmp_path / "out", run_id="RUN_FIXED")
    marker = first.run_dir / "keep.txt"
    marker.write_text("old result", encoding="utf-8")
    before = _sha(first.clean_path)

    with pytest.raises(RunFolderError, match="không ghi đè"):
        run_engine([src], tmp_path / "out", run_id="RUN_FIXED")

    assert marker.read_text(encoding="utf-8") == "old result"
    assert _sha(first.clean_path) == before


def test_output_columns_and_source_file(tmp_path, make_csv, run_engine, read_out):
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    src = make_csv(in_dir / "sample.csv", [
        make_row("U1", "Other", "QC01", "RTG01"),
        make_row("U2", "Discharge", "QC02", "RTG03"),
    ])
    result = run_engine([src], tmp_path / "out")

    cols_clean, clean = read_out(result.clean_path)
    cols_removed, removed = read_out(result.removed_path)

    assert cols_clean == [*EXPECTED_COLUMNS, "Source_File", "Report_Month"]
    assert cols_removed == [*EXPECTED_COLUMNS, "Source_File", "Report_Month", "Rule_ID", "Removal_Reason"]
    assert all(r["Source_File"] == "sample.csv" for r in clean + removed)
    assert result.clean_path.name == CLEAN_FILE_NAME
    assert result.removed_path.name == REMOVED_FILE_NAME


def test_month_comes_from_time_completed_not_file_name(tmp_path, make_csv, run_engine, read_out):
    rows = [
        make_row("A1", "Yard Move", "QC01", "RTG01", **{"Time Completed": "26-Aug-14 2359"}),
        make_row("A2", "Yard Move", "QC01", "RTG01", **{"Time Completed": "26-Sep-02 0005"}),
    ]
    src = make_csv(tmp_path / "random_name_without_month.csv", rows)
    result = run_engine([src], tmp_path / "out")

    _, clean = read_out(result.clean_path)
    months = {r["Unit Nbr"]: r["Report_Month"] for r in clean}
    assert months == {"A1": "2026-08", "A2": "2026-09"}
    assert [m.month for m in result.stats.months] == ["2026-08", "2026-09"]


@pytest.mark.parametrize("bad_value", [
    "2026-08-14 2359",
    "26-Feb-30 1200",
    "26-Xyz-14 1200",
    "26-Aug-14 2460",
    "",
])
def test_invalid_time_completed_stops_the_run(tmp_path, make_csv, run_engine, bad_value):
    src = make_csv(tmp_path / "bad.csv", [
        make_row("OK1", "Yard Move", "QC01", "RTG01"),
        make_row("BAD", "Yard Move", "QC01", "RTG01", **{"Time Completed": bad_value}),
    ])
    out = tmp_path / "out"
    with pytest.raises(DataFormatError, match="Time Completed"):
        run_engine([src], out)

    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    assert not (run_dirs[0] / CLEAN_FILE_NAME).exists()
    manifest = json.loads((run_dirs[0] / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert "DataFormatError" in manifest["error"]


def test_raw_file_is_unchanged_and_hashes_are_recorded(tmp_path, make_csv, run_engine):
    src = make_csv(tmp_path / "in.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    original = _sha(src)
    result = run_engine([src], tmp_path / "out")

    assert _sha(src) == original
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "SUCCESS"
    entry = manifest["inputs"][0]
    assert entry["sha256_before"] == original
    assert entry["sha256_after"] == original


def test_manifest_records_settings_timings_and_counts(tmp_path, make_csv, run_engine):
    src = make_csv(tmp_path / "in.csv", [
        make_row("U1", "Other", "QC01", "RTG01"),
        make_row("U2", "Yard Move", "QC01", "RTG01"),
    ])
    settings = EngineSettings(memory_limit="512MB", temp_directory=tmp_path / "duck_tmp")
    result = run_engine([src], tmp_path / "out", settings=settings)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["settings"]["memory_limit"] == "512MB"
    assert manifest["counts"]["raw_total"] == 2
    assert manifest["counts"]["removed_total"] == 1
    assert manifest["counts"]["clean_total"] == 1
    assert manifest["counts"]["reconciliation"] == "OK"
    assert {"validate", "load", "write_clean", "write_removed", "stats", "integrity", "summary"} <= set(
        manifest["timings_seconds"])


def test_engine_temp_directory_is_removed_after_run(tmp_path, make_csv, run_engine):
    src = make_csv(tmp_path / "in.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    temp_root = tmp_path / "duck_tmp"
    result = run_engine([src], tmp_path / "out", settings=EngineSettings(temp_directory=temp_root))
    assert not (temp_root / result.run_id).exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["temp_dir_removed"] is True


def test_raw_equals_clean_plus_removed_across_files_and_months(tmp_path, make_csv, run_engine):
    a = make_csv(tmp_path / "first.csv", [
        make_row("A1", "Other", "QC01", "RTG01"),
        make_row("A2", "Load", "QC01", "QC02"),
    ])
    b = make_csv(tmp_path / "second.csv", [
        make_row("B1", "Load", None, None, **{"Time Completed": "26-Sep-02 0005"}),
        make_row("B2", "Yard Move", None, "RTG05"),
        make_row("B3", "Discharge", "RTG01", None),
    ])
    result = run_engine([a, b], tmp_path / "out")
    s = result.stats

    assert s.raw_total == 5
    assert s.clean_total + s.removed_total == s.raw_total
    per_file = {f.name: f for f in s.files}
    assert per_file["first.csv"].raw == 2
    assert per_file["second.csv"].raw == 3
    per_month = {m.month: m for m in s.months}
    assert per_month["2026-08"].raw == 2
    assert per_month["2026-09"].raw == 3


def test_summary_workbook_has_expected_sheets(tmp_path, make_csv, run_engine):
    src = make_csv(tmp_path / "s.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    result = run_engine([src], tmp_path / "out")

    assert result.summary_path.name == SUMMARY_FILE_NAME
    wb = openpyxl.load_workbook(result.summary_path, read_only=True)
    assert wb.sheetnames == [
        "Overview", "By_File", "By_Month", "By_Rule", "Rule_Overlap", "Warnings", "Reconciliation",
    ]


def test_warnings_for_blank_and_malformed_time_of_fetch(tmp_path, make_csv, run_engine):
    rows = [
        make_row("U1", "Yard Move", "QC01", "RTG01", **{"Time of Fetch": ""}),
        make_row("U2", "Yard Move", "QC01", "RTG01", **{"Time of Fetch": "garbage"}),
    ]
    src = make_csv(tmp_path / "w.csv", rows)
    result = run_engine([src], tmp_path / "out")
    f = result.stats.files[0]
    assert f.blank_time_of_fetch == 1
    assert f.invalid_time_of_fetch == 1
    assert result.stats.raw_total == 2


def test_unknown_move_kind_is_reported_not_removed(tmp_path, make_csv, run_engine, read_out):
    src = make_csv(tmp_path / "u.csv", [make_row("U1", "Mystery", "QC01", "RTG01")])
    result = run_engine([src], tmp_path / "out")
    _, clean = read_out(result.clean_path)
    assert len(clean) == 1
    assert result.stats.unknown_move_kinds == [("u.csv", "MYSTERY", 1)]


def test_quoted_comma_value_is_preserved(tmp_path, make_csv, run_engine, read_out):
    src = make_csv(tmp_path / "q.csv", [make_row("U1", "Yard Move", "QC01", "RTG01",
                                                 **{"To Position": "Y-A,B-1"})])
    result = run_engine([src], tmp_path / "out")
    _, clean = read_out(result.clean_path)
    assert clean[0]["To Position"] == "Y-A,B-1"


def test_renamed_header_produces_standard_column_names(tmp_path, make_csv, run_engine, read_out):
    cols = tuple(c.lower() if c == "Move Kind" else c for c in EXPECTED_COLUMNS)
    src = make_csv(tmp_path / "h.csv", [make_row("U1", "Yard Move", "QC01", "RTG01")], columns=cols)
    result = run_engine([src], tmp_path / "out")
    cols_clean, _ = read_out(result.clean_path)
    assert cols_clean[:13] == list(EXPECTED_COLUMNS)


def test_progress_callback_receives_stages(tmp_path, make_csv):
    stages: list[str] = []
    src = make_csv(tmp_path / "p.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    engine = CleaningEngine(progress=lambda stage, msg, frac: stages.append(stage))
    engine.run([src], tmp_path / "out")
    assert stages[0] == "validate"
    assert stages[-1] == "done"
    assert "write" in stages and "integrity" in stages and "summary" in stages


def test_invalid_input_writes_no_results(tmp_path, run_engine):
    out = tmp_path / "out"
    with pytest.raises(InputError):
        run_engine([tmp_path / "missing.csv"], out)
    run_dir = next(out.iterdir())
    assert not (run_dir / CLEAN_FILE_NAME).exists()
    assert not (run_dir / REMOVED_FILE_NAME).exists()
    manifest = json.loads((run_dir / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"


def test_precheck_reports_months_and_invalid_rows_without_writing(tmp_path, make_csv):
    src = make_csv(tmp_path / "pc.csv", [
        make_row("A1", "Other", "QC01", "RTG01"),
        make_row("A2", "Load", None, None, **{"Time Completed": "26-Sep-02 0005"}),
        make_row("A3", "Load", None, None, **{"Time Completed": "26-Feb-30 0005"}),
    ])
    result = precheck([src])
    assert result.rows_total == 3
    assert result.invalid_total == 1
    assert result.months == ["2026-08", "2026-09"]
    assert result.files[0].months == ["2026-08", "2026-09"]
    assert not result.ok
    assert not any(tmp_path.rglob("clean_data.parquet"))


def test_precheck_rejects_structure_errors(tmp_path, make_csv):
    src = make_csv(tmp_path / "bad.csv", [], columns=EXPECTED_COLUMNS[:-1])
    with pytest.raises(InputError, match="thiếu cột"):
        precheck([src])
