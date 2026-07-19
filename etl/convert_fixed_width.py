"""
Convert a legacy fixed-width ED wait-time extract to CSV.

Mirrors the kind of SAS PROC EXPORT / FILE PRINT dump hospitals still
hand off when modern APIs aren't available. Spec matches
scripts/generate_sample_raw.py FIXED_WIDTH_SPEC.
"""

from __future__ import annotations

import csv
from pathlib import Path

SPEC = [
    ("Hospital_Name", 0, 45),
    ("OH_Region", 45, 57),
    ("Peer_Group", 57, 75),
    ("Reporting_Period", 75, 85),
    ("Indicator_Code", 85, 103),
    ("Avg_Hours", 103, 111),
    ("Patient_Volume", 111, 119),
    ("Pct_Within_Target", 119, 127),
    ("Target_Hours", 127, 133),
]


def parse_line(line: str) -> dict[str, str]:
    # Pad short lines so slicing is safe
    padded = line.rstrip("\n").ljust(133)
    return {name: padded[start:end].strip() for name, start, end in SPEC}


def convert(dat_path: Path, csv_path: Path) -> int:
    rows = []
    with dat_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(parse_line(line))

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[c[0] for c in SPEC])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    n = convert(
        root / "data" / "raw" / "ed_wait_times_legacy.dat",
        root / "data" / "raw" / "ed_wait_times_from_fixed_width.csv",
    )
    print(f"Converted {n} fixed-width rows → CSV")
