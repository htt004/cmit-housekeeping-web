"""Sinh file CSV tổng hợp để kiểm thử hiệu năng.

Ví dụ:
    python scripts\\generate_synthetic.py --rows 5000000 --out D:\\Bench\\5m
Kết quả: các file synthetic_NN.csv và expected.json (số tham chiếu) nằm NGOÀI thư mục đầu vào.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cleaning.synthetic import SyntheticSpec, generate  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sinh dữ liệu RAW tổng hợp")
    parser.add_argument("--rows", type=int, required=True, help="Tổng số dòng")
    parser.add_argument("--files", type=int, default=0, help="Số file (mặc định: mỗi file tối đa 2 triệu dòng)")
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--out", required=True, help="Thư mục ghi các file CSV")
    args = parser.parse_args(argv)

    files = args.files or max(1, -(-args.rows // 2_000_000))
    out = Path(args.out)
    t0 = time.perf_counter()
    expected = generate(out / "input", SyntheticSpec(rows=args.rows, files=files, seed=args.seed))
    seconds = time.perf_counter() - t0

    expected_path = out / "expected.json"
    expected_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã sinh {args.rows:,} dòng trong {files} file, mất {seconds:,.1f} giây")
    print(f"Đầu vào: {out / 'input'}")
    print(f"Số tham chiếu: {expected_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
