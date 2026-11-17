"""CLI chạy Module 1.

Ví dụ (Windows):
    python run_cleaning.py --input-dir "D:\\Data\\2026" --out "D:\\Output"
    python run_cleaning.py "D:\\Data\\any_name.csv" "D:\\Data\\other.csv" --out "D:\\Output"
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from cleaning.config import ALLOWED_EXTENSIONS
from cleaning.engine import CleaningEngine, EngineSettings
from cleaning.errors import CleaningError


def _csv_files_in(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CMIT Housekeeping – làm sạch dữ liệu (Module 1)")
    parser.add_argument("inputs", nargs="*", help="Các file CSV đầu vào")
    parser.add_argument("--input-dir", help="Thư mục chứa các file .csv")
    parser.add_argument("--out", required=True, help="Thư mục gốc chứa kết quả (mỗi lần chạy một thư mục Run ID)")
    parser.add_argument("--memory-limit", help="Giới hạn bộ nhớ DuckDB, ví dụ 2GB (mặc định: biến CMIT_MEMORY_LIMIT hoặc 2GB)")
    parser.add_argument("--temp-dir", help="Thư mục temp của DuckDB (mặc định: trong thư mục Run)")
    parser.add_argument("--threads", type=int, help="Số luồng DuckDB")
    args = parser.parse_args(argv)

    inputs = [Path(p) for p in args.inputs]
    if args.input_dir:
        inputs += _csv_files_in(Path(args.input_dir))
    if not inputs:
        parser.error("Cần truyền file CSV hoặc --input-dir.")

    env = EngineSettings.from_env()
    settings = EngineSettings(
        memory_limit=args.memory_limit or env.memory_limit,
        temp_directory=Path(args.temp_dir) if args.temp_dir else env.temp_directory,
        threads=args.threads or env.threads,
    )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        result = CleaningEngine(settings=settings).run(inputs, args.out)
    except CleaningError as exc:
        logging.error("%s", exc)
        return 1

    s = result.stats
    print()
    print(f"Run ID:  {result.run_id}")
    print(f"Thư mục: {result.run_dir}")
    print(f"Raw:     {s.raw_total:,}")
    print(f"Clean:   {s.clean_total:,}")
    print(f"Removed: {s.removed_total:,}")
    print(f"Summary: {result.summary_path.name}  |  Manifest: {result.manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
