@echo off
REM Chạy toàn bộ test. Đặt biến để bật test tích hợp với file thật và test scale.
REM   set CMIT_TEST_DATA_DIR=D:\Data\2026
REM   set CMIT_SCALE_ROWS=1000000
REM   set CMIT_MEMORY_LIMIT=1GB
call .venv\Scripts\activate
python -m pytest -v -rs
