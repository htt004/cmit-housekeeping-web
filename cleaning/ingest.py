"""Kiểm tra và khai báo file CSV đầu vào.

Quy tắc:
- Chấp nhận mọi tên file .csv, không yêu cầu quy tắc đặt tên.
- Chỉ kiểm tra 13 cột RAW chuẩn. Tên cột chỉ được chuẩn hóa khi khác nhau về khoảng trắng
  hoặc chữ hoa/thường. Không đoán cột thiếu (ví dụ "Unit Number" không được coi là "Unit Nbr").
- Cột thừa, cột lặp, cột thiếu đều là lỗi. Không bỏ qua file âm thầm.
- Không đọc tháng từ tên file.
"""
from __future__ import annotations

import codecs
import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import (
    ALLOWED_EXTENSIONS,
    EXPECTED_COLUMNS,
    HEADER_PROBE_BYTES,
    READ_CHUNK_BYTES,
    SOURCE_COLUMN,
)
from .errors import CleaningError, EncodingError, InputError, SchemaError
from .rules import quote_ident, sql_str


@dataclass(frozen=True)
class InputFile:
    path: Path
    name: str                                # tên file, dùng làm Source_File
    encoding: str                            # "utf-8" hoặc "utf-16"
    # (tên chuẩn, vị trí cột trong file bắt đầu từ 0, tên gốc trong header), theo thứ tự chuẩn
    column_map: tuple[tuple[str, int, str], ...]


def header_key(name: str) -> str:
    """Khóa so khớp tên cột: bỏ BOM, gộp khoảng trắng, không phân biệt hoa thường."""
    return " ".join(name.replace("\ufeff", "").split()).casefold()


_CANONICAL = {header_key(c): c for c in EXPECTED_COLUMNS}


def _assert_utf8(path: Path) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")()
    offset = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                raise EncodingError(
                    f"{path.name}: không đọc được bằng UTF-8 (khoảng byte {offset + exc.start}). "
                    "Hãy lưu lại file dưới dạng UTF-8 rồi chạy lại."
                ) from exc
            offset += len(chunk)
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        raise EncodingError(f"{path.name}: file kết thúc bằng chuỗi UTF-8 không hợp lệ.") from exc


def detect_encoding(path: Path) -> str:
    with path.open("rb") as fh:
        head = fh.read(2)
    if head in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        return "utf-16"
    _assert_utf8(path)
    return "utf-8"


def read_raw_header(path: Path, encoding: str) -> list[str]:
    """Đọc dòng tiêu đề, giữ nguyên tên gốc (chỉ bỏ BOM)."""
    with path.open("rb") as fh:
        probe = fh.read(HEADER_PROBE_BYTES)
    text = codecs.getincrementaldecoder(encoding)().decode(probe, final=False)
    text = text.lstrip("\ufeff")
    if "\n" not in text and len(probe) >= HEADER_PROBE_BYTES:
        raise SchemaError("dòng tiêu đề dài bất thường")
    first_line = text.split("\n", 1)[0].rstrip("\r")
    if not first_line.strip():
        raise SchemaError("không tìm thấy dòng tiêu đề")
    return next(csv.reader(io.StringIO(first_line)))


def map_columns(raw_headers: Sequence[str]) -> tuple[tuple[str, int, str], ...]:
    """So khớp 13 cột chuẩn. Báo lỗi nếu thiếu, thừa hoặc lặp. Không đoán."""
    mapping: dict[str, tuple[int, str]] = {}
    unexpected: list[str] = []
    duplicated: list[str] = []
    for pos, raw in enumerate(raw_headers):
        canon = _CANONICAL.get(header_key(raw))
        if canon is None:
            unexpected.append(raw)
        elif canon in mapping:
            duplicated.append(raw)
        else:
            mapping[canon] = (pos, raw)

    missing = [c for c in EXPECTED_COLUMNS if c not in mapping]
    problems: list[str] = []
    if missing:
        problems.append(f"thiếu cột {missing}")
    if unexpected:
        problems.append(f"cột không thuộc cấu trúc RAW {unexpected}")
    if duplicated:
        problems.append(f"cột bị lặp {duplicated}")
    if problems:
        raise SchemaError("; ".join(problems))
    return tuple((c, mapping[c][0], mapping[c][1]) for c in EXPECTED_COLUMNS)


def validate_inputs(paths: Sequence[Path]) -> list[InputFile]:
    """Kiểm tra mọi file đầu vào. Gom lỗi và báo một lần, không xử lý phần còn lại khi có lỗi."""
    if not paths:
        raise InputError("Chưa có file đầu vào nào.")

    errors: list[str] = []
    files: list[InputFile] = []
    seen_names: dict[str, Path] = {}

    for raw in paths:
        p = Path(raw)
        if not p.exists():
            errors.append(f"Không tìm thấy file: {p}")
            continue
        if not p.is_file():
            errors.append(f"Đường dẫn không phải file: {p}")
            continue
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            errors.append(f"Không phải file CSV: {p.name}")
            continue
        if p.stat().st_size == 0:
            errors.append(f"File rỗng: {p.name}")
            continue
        if p.name in seen_names:
            errors.append(
                f"Trùng tên file, Source_File sẽ không phân biệt được: "
                f"{p.name} ở {seen_names[p.name]} và {p}"
            )
            continue
        seen_names[p.name] = p

        try:
            encoding = detect_encoding(p)
            column_map = map_columns(read_raw_header(p, encoding))
        except EncodingError as exc:
            errors.append(str(exc))
            continue
        except SchemaError as exc:
            errors.append(f"{p.name}: {exc}")
            continue
        except OSError as exc:
            errors.append(f"Không đọc được {p.name}: {exc}")
            continue

        files.append(InputFile(path=p, name=p.name, encoding=encoding, column_map=column_map))

    if errors:
        raise InputError("Kiểm tra đầu vào thất bại:\n - " + "\n - ".join(errors))
    return files


def source_select(f: InputFile) -> str:
    """SELECT đọc một file bằng DuckDB theo VỊ TRÍ cột (đã kiểm tra đủ 13 cột ở bước validate).

    Đọc theo vị trí để không phụ thuộc cách DuckDB xử lý tên header có khoảng trắng hay BOM.
    Mọi cột là VARCHAR, giữ nguyên giá trị gốc.
    """
    n = len(EXPECTED_COLUMNS)
    cols_decl = ", ".join(f"'c{i}': 'VARCHAR'" for i in range(n))
    select_cols = ", ".join(
        f"{quote_ident(f'c{pos}')} AS {quote_ident(canon)}" for canon, pos, _ in f.column_map
    )
    return (
        f"SELECT {select_cols}, {sql_str(f.name)} AS {quote_ident(SOURCE_COLUMN)} "
        f"FROM read_csv({sql_str(f.path.resolve().as_posix())}, header = false, skip = 1, "
        f"all_varchar = true, delim = ',', quote = {sql_str(chr(34))}, "
        f"encoding = {sql_str(f.encoding)}, columns = {{{cols_decl}}})"
    )
