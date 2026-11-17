"""Test workspace theo phiên dùng cho chế độ chạy thử công khai. Không cần DuckDB."""
from __future__ import annotations

from pathlib import Path

import pytest

import services
from cleaning.errors import InputError


def test_session_ids_are_unique_hex():
    a, b = services.new_session_id(), services.new_session_id()
    assert a != b
    assert len(a) == 32 and all(c in "0123456789abcdef" for c in a)


def test_session_workspaces_are_separate(tmp_path: Path):
    base = services.Workspace(tmp_path).ensure()
    s1 = services.session_workspace(base, services.new_session_id())
    s2 = services.session_workspace(base, services.new_session_id())
    assert s1.root != s2.root
    assert s1.root.parent == base.root / "sessions"


@pytest.mark.parametrize("bad", ["", "../../etc", "ABC", "g" * 32, "a" * 31])
def test_session_id_must_be_hex32(tmp_path: Path, bad: str):
    base = services.Workspace(tmp_path).ensure()
    with pytest.raises(InputError):
        services.session_workspace(base, bad)


def test_delete_workspace_removes_readonly_files(tmp_path: Path):
    base = services.Workspace(tmp_path).ensure()
    ws = services.session_workspace(base, services.new_session_id())
    batch = ws.uploads / "b1"
    batch.mkdir(parents=True)
    f = batch / "a.csv"
    f.write_text("x", encoding="utf-8")
    f.chmod(0o444)
    services.delete_workspace(ws)
    assert not ws.root.exists()
    assert base.root.exists()


def test_delete_workspace_refuses_paths_outside_sessions(tmp_path: Path):
    outside = services.Workspace(tmp_path / "elsewhere").ensure()
    with pytest.raises(InputError):
        services.delete_workspace(outside)
    assert outside.root.exists()
