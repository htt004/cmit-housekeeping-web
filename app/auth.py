"""Xác thực người dùng ở tầng ứng dụng. Không import Streamlit, không import DuckDB.

Hai chế độ, chọn bằng biến môi trường CMIT_AUTH_MODE:
  proxy (mặc định, dùng trên server)  Danh tính lấy từ header do reverse proxy gán sau khi
                                      người dùng đăng nhập (ví dụ X-Auth-Request-Email).
                                      Thiếu header hoặc header không hợp lệ thì từ chối truy cập.
  none  (chỉ dùng trên máy dev)        Không kiểm tra, gán người dùng "local-dev".

Lưu ý bảo mật: chế độ proxy chỉ an toàn khi app không được publish cổng ra ngoài và mọi
request đi qua proxy, proxy là nơi duy nhất ghi đè header này.
"""
from __future__ import annotations

import os
import re
from typing import Mapping, Optional

ENV_AUTH_MODE = "CMIT_AUTH_MODE"
ENV_USER_HEADER = "CMIT_USER_HEADER"
DEFAULT_USER_HEADER = "X-Auth-Request-Email"
DEV_USER = "local-dev"
MODES = ("proxy", "none")

_USER_RE = re.compile(r"[a-z0-9._%+\-@]{3,254}")


class AuthError(Exception):
    """Không xác định được người dùng hoặc cấu hình xác thực sai."""


def auth_mode() -> str:
    mode = os.environ.get(ENV_AUTH_MODE, "proxy").strip().lower()
    if mode not in MODES:
        raise AuthError(f"{ENV_AUTH_MODE} phải là 'proxy' hoặc 'none', hiện là '{mode}'.")
    return mode


def user_header_name() -> str:
    return os.environ.get(ENV_USER_HEADER, DEFAULT_USER_HEADER).strip() or DEFAULT_USER_HEADER


def request_headers(st_module) -> dict[str, str]:
    """Lấy header của request hiện tại. Streamlit >= 1.37 có st.context.headers."""
    ctx = getattr(st_module, "context", None)
    headers = getattr(ctx, "headers", None) or {}
    return dict(headers)


def current_user(
    headers: Mapping[str, str],
    mode: Optional[str] = None,
    header_name: Optional[str] = None,
) -> str:
    """Trả về định danh người dùng (chữ thường). Ném AuthError nếu không hợp lệ."""
    mode = (mode or auth_mode()).lower()
    if mode == "none":
        return DEV_USER
    name = (header_name or user_header_name()).lower()
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    value = lowered.get(name, "").strip().lower()
    if not value:
        raise AuthError(
            "Không xác định được người dùng. Hãy truy cập ứng dụng qua địa chỉ nội bộ đã được cấp "
            "và đăng nhập trước."
        )
    if not _USER_RE.fullmatch(value):
        raise AuthError("Định danh người dùng từ máy chủ không hợp lệ.")
    return value
