"""Truy vết: Run ID, băm SHA-256 file đầu vào, manifest.json cho mỗi lần chạy."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from . import __version__
from .config import HASH_CHUNK_BYTES, RUN_ID_PREFIX
from .rules import Rule


def sha256_file(path: Path) -> str:
    """Băm file theo chunk, không nạp cả file vào RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def new_run_id(now: Optional[datetime] = None) -> str:
    """Run ID dạng RUN_YYYYMMDD_HHMMSS_XXXXXXXX (duy nhất, sắp xếp được theo thời gian)."""
    now = now or datetime.now()
    return f"{RUN_ID_PREFIX}_{now:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8].upper()}"


class RunManifest:
    """Ghi lại đầy đủ một lần chạy để kiểm toán."""

    def __init__(self, run_id: str, run_dir: Path, rules: Iterable[Rule]) -> None:
        self.data: dict[str, Any] = {
            "run_id": run_id,
            "engine_version": __version__,
            "run_dir": run_dir.as_posix(),
            "status": "RUNNING",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "error": None,
            "rules": [{"rule_id": r.rule_id, "description": r.description} for r in rules],
            "inputs": [],
            "counts": {},
            "outputs": {},
        }

    def set_inputs(self, inputs: list[dict]) -> None:
        self.data["inputs"] = inputs

    def update(self, **values: Any) -> None:
        self.data.update(values)

    def finish(self, status: str, error: Optional[str] = None) -> None:
        self.data["status"] = status
        self.data["error"] = error
        self.data["finished_at"] = datetime.now().isoformat(timespec="seconds")

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
