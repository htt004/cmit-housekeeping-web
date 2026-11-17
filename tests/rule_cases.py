"""Bảng case dùng chung cho test rule.

Tuple: (mã case, Move Kind, Fetch CHE, Put CHE, tập Rule_ID kỳ vọng)
Dùng cho cả test engine DuckDB (test_rules.py) và test đối chiếu Python (test_reference.py).
"""
from __future__ import annotations

CASES = [
    # R01
    ("R01-other", "Other", "QC01", "RTG01", {"R01"}),
    ("R01-trim-case", "  other ", "QC01", "RTG01", {"R01"}),
    ("R01-shift-ob", "Shift O.B.", "QC01", "RTG01", {"R01"}),
    ("R01-neg-yard-shift", "Yard Shift", "QC01", "RTG01", set()),
    # R02
    ("R02-load-null-fetch", "Load", None, "QC01", {"R02", "R08"}),
    ("R02-delivery-space-fetch", "Delivery", "   ", "RTG01", {"R02"}),
    ("R02-neg-discharge", "Discharge", None, "RTG01", set()),
    # R03
    ("R03-yard-move-both-blank", "Yard Move", None, None, {"R03"}),
    ("R03-load-both-blank", "Load", None, None, {"R02", "R03"}),
    ("R03-neg-put-filled", "Yard Move", None, "QC01", {"R08"}),
    # R04
    ("R04-rtg16", "Load", "RTG16", "QC01", {"R04"}),
    ("R04-rtg17-case-space", "Load", " rtg17 ", "QC01", {"R04"}),
    ("R04-neg-rtg160", "Load", "RTG160", "QC01", set()),
    # R05
    ("R05-qc01", "Yard Move", "QC01", None, {"R05"}),
    ("R05-qc09-lower", "Yard Move", "qc09", None, {"R05"}),
    ("R05-neg-xqc01", "Yard Move", "XQC01", None, set()),
    # R06: chỉ Discharge và Receival. Không có Receive, Recieve.
    ("R06-discharge", "Discharge", "RTG01", None, {"R06"}),
    ("R06-receival", "Receival", "RTG01", None, {"R06"}),
    ("R06-receival-lower", "receival", "RTG01", None, {"R06"}),
    ("R06-neg-load", "Load", "RTG01", None, set()),
    ("R06-neg-recieve", "Recieve", "RTG01", None, set()),
    ("R06-neg-receive", "Receive", "RTG01", None, set()),
    # R07
    ("R07-rtg16", "Load", "QC01", "RTG16", {"R07"}),
    ("R07-rtg17-lower", "Load", "QC01", "rtg17", {"R07"}),
    ("R07-neg-qc02", "Load", "QC01", "QC02", set()),
    # R08
    ("R08-yard-move", "Yard Move", None, "QC05", {"R08"}),
    # Nhiều rule trùng nhau
    ("MULTI-R01-R04-R07", "Other", "RTG16", "RTG17", {"R01", "R04", "R07"}),
    ("MULTI-R02-R07", "Load", None, "RTG16", {"R02", "R07"}),
    ("MULTI-R05-R06", "Discharge", "QC01", None, {"R05", "R06"}),
    ("MULTI-R02-R03-delivery", "Delivery", None, None, {"R02", "R03"}),
]
