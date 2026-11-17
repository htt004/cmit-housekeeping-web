"""Test cho lớp xác thực, workspace theo người dùng và script dọn dữ liệu. Không cần DuckDB."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

import auth
import services
from scripts import purge_workspace


# ---------------------------------------------------------------- auth

def test_none_mode_returns_dev_user():
    assert auth.current_user({}, mode="none") == auth.DEV_USER


def test_proxy_mode_requires_header():
    with pytest.raises(auth.AuthError):
        auth.current_user({}, mode="proxy", header_name="X-Auth-Request-Email")


def test_proxy_mode_header_is_case_insensitive_and_lowercased():
    headers = {"x-auth-request-email": "  Nguyen.Van.A@CMIT.local "}
    assert auth.current_user(headers, mode="proxy") == "nguyen.van.a@cmit.local"


def test_proxy_mode_rejects_invalid_identity():
    with pytest.raises(auth.AuthError):
        auth.current_user({"X-Auth-Request-Email": "a b<script>"}, mode="proxy")


def test_auth_mode_env_validation(monkeypatch):
    monkeypatch.setenv(auth.ENV_AUTH_MODE, "anonymous")
    with pytest.raises(auth.AuthError):
        auth.auth_mode()
    monkeypatch.delenv(auth.ENV_AUTH_MODE, raising=False)
    assert auth.auth_mode() == "proxy"  # mặc định an toàn


def test_request_headers_without_streamlit_context():
    class FakeSt:
        pass

    assert auth.request_headers(FakeSt()) == {}


# ---------------------------------------------------------------- workspace theo người dùng

def test_user_workspaces_are_isolated(tmp_path: Path):
    base = services.Workspace(tmp_path).ensure()
    a = services.user_workspace(base, "a@cmit.local")
    b = services.user_workspace(base, "b@cmit.local")
    assert a.root != b.root
    assert a.outputs != b.outputs
    assert a.root.is_relative_to(base.root / "users")


def test_user_workspace_is_stable_and_case_insensitive(tmp_path: Path):
    base = services.Workspace(tmp_path).ensure()
    first = services.user_workspace(base, "A@cmit.local")
    second = services.user_workspace(base, "a@CMIT.local")
    assert first.root == second.root
    assert (first.root / "owner.txt").read_text(encoding="utf-8").strip() == "a@cmit.local"


def test_user_workspace_name_does_not_expose_email(tmp_path: Path):
    base = services.Workspace(tmp_path).ensure()
    ws = services.user_workspace(base, "secret.person@cmit.local")
    assert "secret" not in ws.root.name


def test_list_runs_only_shows_own_runs(tmp_path: Path):
    import json

    base = services.Workspace(tmp_path).ensure()
    a = services.user_workspace(base, "a@cmit.local")
    b = services.user_workspace(base, "b@cmit.local")
    run = a.outputs / "RUN_20261117_100000_deadbeef"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"run_id": run.name, "status": "SUCCESS"}), encoding="utf-8")
    assert [r.run_id for r in services.list_runs(a)] == [run.name]
    assert services.list_runs(b) == []


# ---------------------------------------------------------------- dọn dữ liệu

def _make_batch(root: Path, user: str, batch: str, age_days: float) -> Path:
    d = root / "users" / user / "uploads" / batch
    d.mkdir(parents=True)
    f = d / "a.csv"
    f.write_text("x", encoding="utf-8")
    old = time.time() - age_days * 86400
    os.utime(f, (old, old))
    os.utime(d, (old, old))
    return d


def test_purge_dry_run_deletes_nothing(tmp_path: Path):
    old = _make_batch(tmp_path, "u1", "old", 40)
    rc = purge_workspace.main(["--workspace", str(tmp_path), "--days", "30"])
    assert rc == 0
    assert old.exists()


def test_purge_apply_removes_old_uploads_only(tmp_path: Path):
    old = _make_batch(tmp_path, "u1", "old", 40)
    new = _make_batch(tmp_path, "u1", "new", 1)
    rc = purge_workspace.main(["--workspace", str(tmp_path), "--days", "30", "--apply"])
    assert rc == 0
    assert not old.exists()
    assert new.exists()


def test_purge_rejects_nonpositive_days(tmp_path: Path):
    assert purge_workspace.main(["--workspace", str(tmp_path), "--days", "0"]) == 2
