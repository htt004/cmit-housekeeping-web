@echo off
REM Mở giao diện Streamlit trên máy dev. CMIT_AUTH_MODE=none chỉ dành cho máy cá nhân.
REM Trên server dùng docker compose (xem DEPLOY.md), không dùng file này.
REM Workspace mặc định: .\workspace (đổi bằng biến CMIT_WORKSPACE).
call .venv\Scripts\activate
set CMIT_AUTH_MODE=none
streamlit run app\streamlit_app.py
