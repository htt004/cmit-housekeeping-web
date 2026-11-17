"""Test lớp service của giao diện: lưu upload, quyền chỉ đọc, danh sách lần chạy. Thuần Python."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import services  # noqa: E402
from cleaning.config import MANIFEST_FILE_NAME  # noqa: E402
from cleaning.errors import InputError  # noqa: E402


class FakeUpload:
    """Đối tượng giả lập UploadedFile của Streamlit."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self):
        return memoryview(self._data)


@pytest.fixture
def ws(tmp_path) -> services.Workspace:
    return services.Workspace(tmp_path / "ws").ensure()


def test_save_uploads_keeps_any_csv_name_and_strips_directories(ws):
    batch = services.new_batch_id()
    saved = services.save_uploads(
        [FakeUpload("..\\evil/dir name v2.csv", b"a,b\r\n"), FakeUpload("Plain.CSV", b"x")],
        batch, ws,
    )
    names = sorted(p.name for p in saved)
    assert names == ["Plain.CSV", "dir name v2.csv"]
    assert all(p.parent == services.batch_dir(ws, batch) for p in saved)


def test_saved_uploads_are_read_only(ws):
    batch = services.new_batch_id()
    (saved,) = services.save_uploads([FakeUpload("raw.csv", b"data")], batch, ws)
    if os.name != "nt":  # trên Windows quyền chỉ đọc chỉ là cờ thuộc tính, vẫn kiểm tra được
        assert not os.access(saved, os.W_OK) or stat.S_IMODE(saved.stat().st_mode) == 0o444
    assert saved.read_bytes() == b"data"


def test_non_csv_upload_is_rejected_and_nothing_partial_is_kept_silently(ws):
    batch = services.new_batch_id()
    with pytest.raises(InputError, match="Không phải file CSV"):
        services.save_uploads([FakeUpload("ok.csv", b"1"), FakeUpload("bad.xlsx", b"2")], batch, ws)
    # file hợp lệ vẫn được ghi, nhưng lỗi được báo rõ (không im lặng bỏ qua)
    assert [p.name for p in services.list_batch_files(ws, batch)] == ["ok.csv"]


def test_duplicate_name_in_same_batch_is_rejected(ws):
    batch = services.new_batch_id()
    services.save_uploads([FakeUpload("same.csv", b"1")], batch, ws)
    with pytest.raises(InputError, match="Trùng tên"):
        services.save_uploads([FakeUpload("same.csv", b"2")], batch, ws)
    assert (services.batch_dir(ws, batch) / "same.csv").read_bytes() == b"1"


def test_list_runs_reads_manifests_newest_first(ws):
    for rid, started in [("RUN_A", "2026-11-17T10:00:00"), ("RUN_B", "2026-11-17T12:00:00")]:
        d = ws.outputs / rid
        d.mkdir(parents=True)
        (d / MANIFEST_FILE_NAME).write_text(json.dumps({
            "run_id": rid, "status": "SUCCESS", "started_at": started,
            "counts": {"raw_total": 5, "clean_total": 3, "removed_total": 2},
        }), encoding="utf-8")
    (ws.outputs / "not_a_run").mkdir()  # thư mục không có manifest bị bỏ qua

    runs = services.list_runs(ws)
    assert [r.run_id for r in runs] == ["RUN_B", "RUN_A"]
    assert runs[0].raw_total == 5 and runs[0].removed_total == 2


def test_output_path_rejects_unknown_dataset(tmp_path):
    with pytest.raises(ValueError):
        services.output_path(tmp_path, "../../etc")


def test_workspace_from_env_respects_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("CMIT_WORKSPACE", str(tmp_path / "custom"))
    ws = services.workspace_from_env()
    assert ws.root == (tmp_path / "custom").resolve()
    assert ws.uploads.exists() and ws.outputs.exists()
