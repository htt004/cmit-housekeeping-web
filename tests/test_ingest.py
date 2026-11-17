"""Test kiểm tra đầu vào: tên file, encoding, cấu trúc 13 cột, chuẩn hóa tên cột."""
from __future__ import annotations

import pytest

from cleaning.config import EXPECTED_COLUMNS
from cleaning.errors import InputError
from cleaning.ingest import detect_encoding, validate_inputs
from conftest import make_row


def test_any_csv_name_is_accepted(tmp_path, make_csv):
    p = make_csv(tmp_path / "bất kỳ tên nào 2 final.CSV", [make_row("U1", "Other", "QC01", "RTG01")])
    files = validate_inputs([p])
    assert files[0].name == "bất kỳ tên nào 2 final.CSV"


def test_non_csv_extension_is_rejected(tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(InputError, match="Không phải file CSV"):
        validate_inputs([p])


def test_utf8_with_bom_is_accepted(tmp_path, make_csv):
    p = make_csv(tmp_path / "a.csv", [make_row("U1", "Other", "QC01", "RTG01")], bom=True)
    files = validate_inputs([p])
    assert files[0].encoding == "utf-8"


def test_utf16_detected_by_bom(tmp_path, make_csv):
    p = make_csv(tmp_path / "u16.csv", [make_row("U1", "Other", "QC01", "RTG01")], encoding="utf-16")
    assert detect_encoding(p) == "utf-16"


def test_non_utf8_bytes_raise_clear_error(tmp_path):
    header = ",".join(EXPECTED_COLUMNS).encode("utf-8")
    body = b"U1,Other,Y-1,Y-2,,QC01,RTG01,26-Aug-14 2359,26-Aug-14 2351,Export,MAE,VNBDG,FCL\xe9\r\n"
    p = tmp_path / "bad.csv"
    p.write_bytes(header + b"\r\n" + body)
    with pytest.raises(InputError, match="UTF-8"):
        validate_inputs([p])


def test_missing_column_is_reported_and_not_guessed(tmp_path, make_csv):
    cols = tuple("Unit Number" if c == "Unit Nbr" else c for c in EXPECTED_COLUMNS)
    p = make_csv(tmp_path / "x.csv", [], columns=cols)
    with pytest.raises(InputError, match="thiếu cột"):
        validate_inputs([p])


def test_unexpected_extra_column_is_rejected(tmp_path, make_csv):
    p = make_csv(tmp_path / "x.csv", [], columns=EXPECTED_COLUMNS + ("Extra Col",))
    with pytest.raises(InputError, match="không thuộc cấu trúc RAW"):
        validate_inputs([p])


def test_duplicate_header_is_rejected(tmp_path, make_csv):
    cols = EXPECTED_COLUMNS + ("unit nbr",)
    p = make_csv(tmp_path / "x.csv", [], columns=cols)
    with pytest.raises(InputError, match="lặp"):
        validate_inputs([p])


def test_header_case_and_spacing_are_normalized(tmp_path, make_csv):
    cols = tuple(
        "  " + c.upper().replace(" ", "   ") + " " if i % 2 == 0 else c.lower()
        for i, c in enumerate(EXPECTED_COLUMNS)
    )
    p = make_csv(tmp_path / "x.csv", [make_row("U1", "Other", "QC01", "RTG01")], columns=cols)
    files = validate_inputs([p])
    canon = [c for c, _, _ in files[0].column_map]
    assert canon == list(EXPECTED_COLUMNS)


def test_column_order_may_differ_and_output_uses_standard_order(tmp_path, make_csv):
    shuffled = tuple(reversed(EXPECTED_COLUMNS))
    p = make_csv(tmp_path / "x.csv", [make_row("U1", "Other", "QC01", "RTG01")], columns=shuffled)
    files = validate_inputs([p])
    assert [c for c, _, _ in files[0].column_map] == list(EXPECTED_COLUMNS)
    # Vị trí phải khớp với thứ tự thực tế trong file (đảo ngược)
    assert [pos for _, pos, _ in files[0].column_map] == list(range(len(EXPECTED_COLUMNS) - 1, -1, -1))


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(InputError, match="Không tìm thấy file"):
        validate_inputs([tmp_path / "does_not_exist.csv"])


def test_empty_file_is_reported(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    with pytest.raises(InputError, match="rỗng"):
        validate_inputs([p])


def test_same_file_name_in_two_folders_is_rejected(tmp_path, make_csv):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    a = make_csv(d1 / "x.csv", [make_row("U1", "Other", "QC01", "RTG01")])
    b = make_csv(d2 / "x.csv", [make_row("U2", "Other", "QC01", "RTG01")])
    with pytest.raises(InputError, match="Trùng tên file"):
        validate_inputs([a, b])


def test_all_errors_are_reported_together(tmp_path):
    with pytest.raises(InputError) as exc:
        validate_inputs([tmp_path / "nope1.csv", tmp_path / "nope2.csv"])
    assert "nope1.csv" in str(exc.value)
    assert "nope2.csv" in str(exc.value)


def test_no_inputs_is_rejected():
    with pytest.raises(InputError, match="Chưa có file"):
        validate_inputs([])
