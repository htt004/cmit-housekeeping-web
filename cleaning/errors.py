"""Các loại lỗi của Module 1. Thông báo bằng tiếng Việt."""
from __future__ import annotations


class CleaningError(Exception):
    """Lỗi gốc của engine."""


class InputError(CleaningError):
    """Đầu vào không hợp lệ: thiếu file, sai định dạng, trùng tên..."""


class EncodingError(InputError):
    """File không đọc được với encoding được hỗ trợ."""


class SchemaError(InputError):
    """Cấu trúc cột không khớp RAW chuẩn."""


class DataFormatError(InputError):
    """Dữ liệu không đọc được, ví dụ Time Completed sai định dạng hoặc không phải ngày hợp lệ."""


class RunFolderError(CleaningError):
    """Không tạo được thư mục kết quả riêng cho lần chạy (đã tồn tại, không ghi đè)."""


class RawIntegrityError(CleaningError):
    """File RAW bị thay đổi trong lúc chạy."""


class ReconciliationError(CleaningError):
    """Raw Rows != Clean Rows + Removed Rows."""
