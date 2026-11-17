"""Cấu hình cố định của Module 1.

Cấu trúc 13 cột lấy từ RAW DATA mẫu (Aug/Sep/Oct 2026). Engine chỉ kiểm tra đúng 13 cột này.
"""
from __future__ import annotations

EXPECTED_COLUMNS: tuple[str, ...] = (
    "Unit Nbr",
    "Move Kind",
    "From Position",
    "To Position",
    "Crane CHE Name",
    "Fetch CHE Name",
    "Put CHE Name",
    "Time Completed",
    "Time of Fetch",
    "Unit Category",
    "Line Op",
    "Unit POD",
    "Unit Frght Kind",
)

COL_UNIT = "Unit Nbr"
COL_MOVE = "Move Kind"
COL_FROM = "From Position"
COL_TO = "To Position"
COL_CRANE = "Crane CHE Name"
COL_FETCH = "Fetch CHE Name"
COL_PUT = "Put CHE Name"
COL_TIME_COMPLETED = "Time Completed"
COL_TIME_FETCH = "Time of Fetch"

SOURCE_COLUMN = "Source_File"
REPORT_MONTH_COLUMN = "Report_Month"

ALLOWED_EXTENSIONS: tuple[str, ...] = (".csv",)

DUPLICATE_KEY_COLUMNS: tuple[str, ...] = (
    COL_UNIT,
    COL_MOVE,
    COL_FROM,
    COL_TO,
    COL_TIME_COMPLETED,
)

KNOWN_MOVE_KINDS: frozenset[str] = frozenset(
    {
        "DISCHARGE",
        "LOAD",
        "YARD MOVE",
        "DELIVERY",
        "RECEIVAL",
        "OTHER",
        "YARD SHIFT",
        "SHIFT O.B.",
    }
)

READ_CHUNK_BYTES = 8 * 1024 * 1024
HEADER_PROBE_BYTES = 256 * 1024
HASH_CHUNK_BYTES = 8 * 1024 * 1024

# Giới hạn tài nguyên DuckDB. Có thể ghi đè bằng biến môi trường.
DEFAULT_MEMORY_LIMIT = "2GB"
ENV_MEMORY_LIMIT = "CMIT_MEMORY_LIMIT"
ENV_TEMP_DIR = "CMIT_TEMP_DIR"
ENV_THREADS = "CMIT_THREADS"
ENV_WORKSPACE = "CMIT_WORKSPACE"
TEMP_DIR_NAME = "_duckdb_tmp"

RUN_ID_PREFIX = "RUN"
CLEAN_FILE_NAME = "clean_data.parquet"
REMOVED_FILE_NAME = "removed_data.parquet"
SUMMARY_FILE_NAME = "cleaning_summary.xlsx"
MANIFEST_FILE_NAME = "manifest.json"
LOG_FILE_NAME = "cleaning.log"
