"""Sinh dữ liệu RAW tổng hợp (cùng 13 cột) để kiểm thử hiệu năng và đối chiếu.

Số đếm tham chiếu được tính bằng cleaning/reference.py ngay lúc ghi file, nên không cần
đọc lại file để kiểm chứng. Phân bố giá trị gần đúng với dữ liệu thật, nhưng không phải dữ liệu thật.
"""
from __future__ import annotations

import csv
import random
import string
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .config import EXPECTED_COLUMNS
from .reference import classify_row
from .rules import MONTHS

MOVE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("Discharge", 40.0),
    ("Load", 40.0),
    ("Yard Move", 12.0),
    ("Delivery", 4.0),
    ("Receival", 3.0),
    ("Other", 0.5),
    ("Yard Shift", 0.3),
    ("Shift O.B.", 0.2),
)
QC = tuple(f"QC{i:02d}" for i in range(1, 8))
RTG = tuple(f"RTG{i:02d}" for i in range(1, 16))
RTG_VIRTUAL = ("RTG16", "RTG17")
OTHER_CHE = ("EH01", "EH02", "UN02", "UN03", "RS01", "RS02", "LRS01", "HC01", "TC21")
CATEGORIES = ("Export", "Import", "Storage", "Transship", "Domestic", "Through")
LINE_OPS = ("MAE", "HLC", "ZIM", "ESL", "ONE", "RCL")
PODS = ("VNBDG", "VNCMT", "CNYTN", "ESVLC", "INMUN")


@dataclass(frozen=True)
class SyntheticSpec:
    rows: int
    files: int = 1
    months: tuple[str, ...] = ("2026-08", "2026-09", "2026-10")
    seed: int = 20261117


# Tỷ lệ hiệu chỉnh gần với dữ liệu thật (RAW Aug–Oct): ô trống ~2%, RTG16/17 ~2,5%.
BLANK_RATE = 0.02
VIRTUAL_RATE = 0.025


def _che(rng: random.Random) -> str:
    r = rng.random()
    if r < BLANK_RATE:
        return ""
    if r < BLANK_RATE + 0.003:
        return "   "
    if r < BLANK_RATE + 0.005:
        return rng.choice(["rtg17", " qc03 ", "RTG16"])
    u = rng.random()
    if u < VIRTUAL_RATE:
        return rng.choice(RTG_VIRTUAL)
    if u < VIRTUAL_RATE + 0.01:
        return rng.choice(OTHER_CHE)
    if u < VIRTUAL_RATE + 0.01 + 0.30:
        return rng.choice(QC)
    return rng.choice(RTG)


def _time_text(rng: random.Random, month_key: str) -> str:
    year, month = int(month_key[:4]), int(month_key[5:7])
    return (
        f"{year % 100:02d}-{MONTHS[month - 1]}-{rng.randint(1, 28):02d} "
        f"{rng.randint(0, 23):02d}{rng.randint(0, 59):02d}"
    )


def _position(rng: random.Random) -> str:
    a, b = rng.choice(string.ascii_uppercase), rng.choice(string.ascii_uppercase)
    return f"Y-CMIT-{rng.randint(1, 9)}{a}{rng.randint(1, 99):02d}{b}.{rng.randint(1, 4)}"


def generate(out_dir: Path, spec: SyntheticSpec) -> dict:
    """Ghi spec.files file CSV vào out_dir. Trả về số đếm tham chiếu (không ghi ra đĩa)."""
    if spec.rows < 0 or spec.files < 1:
        raise ValueError("rows phải >= 0 và files phải >= 1")
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(spec.seed)
    moves = [m for m, _ in MOVE_WEIGHTS]
    weights = [w for _, w in MOVE_WEIGHTS]

    file_counts: dict[str, Counter] = {}
    month_counts: dict[str, Counter] = defaultdict(Counter)

    for i in range(spec.files):
        n = spec.rows // spec.files + (1 if i < spec.rows % spec.files else 0)
        name = f"synthetic_{i + 1:02d}.csv"
        fc: Counter = Counter()
        with (out_dir / name).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\r\n")
            writer.writerow(EXPECTED_COLUMNS)
            for _ in range(n):
                month_key = rng.choice(spec.months)
                tf = "" if rng.random() < 0.01 else _time_text(rng, month_key)
                row = {
                    "Unit Nbr": "".join(rng.choices(string.ascii_uppercase, k=4))
                    + str(rng.randrange(1_000_000, 10_000_000)),
                    "Move Kind": rng.choices(moves, weights)[0],
                    "From Position": _position(rng),
                    "To Position": _position(rng),
                    "Crane CHE Name": rng.choice(QC),
                    "Fetch CHE Name": _che(rng),
                    "Put CHE Name": _che(rng),
                    "Time Completed": _time_text(rng, month_key),
                    "Time of Fetch": tf,
                    "Unit Category": rng.choice(CATEGORIES),
                    "Line Op": rng.choice(LINE_OPS),
                    "Unit POD": rng.choice(PODS),
                    "Unit Frght Kind": rng.choice(("FCL", "Empty")),
                }
                writer.writerow([row[c] for c in EXPECTED_COLUMNS])

                month, ids = classify_row(row)
                if month is None:  # không thể xảy ra với dữ liệu sinh ra, nhưng kiểm tra cho chắc
                    raise AssertionError("Generator tạo Time Completed không hợp lệ")
                key = "removed" if ids else "clean"
                fc["raw"] += 1
                fc[key] += 1
                month_counts[month]["raw"] += 1
                month_counts[month][key] += 1
        file_counts[name] = fc

    total = Counter()
    for c in file_counts.values():
        total.update(c)
    return {
        "rows": spec.rows,
        "files": {k: dict(v) for k, v in file_counts.items()},
        "months": {k: dict(v) for k, v in sorted(month_counts.items())},
        "total": dict(total),
    }
