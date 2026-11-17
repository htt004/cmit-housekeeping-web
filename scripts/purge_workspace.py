"""Dọn dữ liệu cũ trong workspace theo thời hạn lưu giữ.

Mặc định chỉ liệt kê (dry-run), không xóa gì. Phải thêm --apply để xóa.
Mặc định chỉ xóa batch upload (bản sao CSV). Kết quả (outputs) chỉ bị xóa khi thêm --include-outputs,
vì đó là bản ghi kiểm toán.

Ví dụ (trên server, chạy trong container):
  docker compose exec app python scripts/purge_workspace.py --days 30
  docker compose exec app python scripts/purge_workspace.py --days 30 --apply
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import time
from pathlib import Path


def _newest_mtime(path: Path) -> float:
    newest = path.stat().st_mtime
    for p in path.rglob("*"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest


def _clear_readonly(func, path, _exc_info) -> None:
    # File upload có quyền chỉ đọc. Windows không xóa được nếu không bỏ thuộc tính này.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def find_targets(root: Path, days: int, include_outputs: bool) -> list[Path]:
    cutoff = time.time() - days * 86400
    targets: list[Path] = []
    users = root / "users"
    if not users.is_dir():
        return targets
    for user_dir in sorted(p for p in users.iterdir() if p.is_dir()):
        groups = ["uploads"] + (["outputs"] if include_outputs else [])
        for group in groups:
            gdir = user_dir / group
            if not gdir.is_dir():
                continue
            for item in sorted(p for p in gdir.iterdir() if p.is_dir()):
                if _newest_mtime(item) < cutoff:
                    targets.append(item)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", default=os.environ.get("CMIT_WORKSPACE", "workspace"))
    parser.add_argument("--days", type=int, required=True, help="Xóa mục không thay đổi trong N ngày")
    parser.add_argument("--include-outputs", action="store_true", help="Cũng xóa kết quả (outputs)")
    parser.add_argument("--apply", action="store_true", help="Thực sự xóa. Không có thì chỉ liệt kê.")
    args = parser.parse_args(argv)

    if args.days < 1:
        print("--days phải >= 1", file=sys.stderr)
        return 2
    root = Path(args.workspace).resolve()
    targets = find_targets(root, args.days, args.include_outputs)
    mode = "XÓA" if args.apply else "DRY-RUN (chưa xóa)"
    print(f"{mode}: {len(targets)} mục cũ hơn {args.days} ngày trong {root}")
    for t in targets:
        print(f"  {t}")
        if args.apply:
            shutil.rmtree(t, onerror=_clear_readonly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
