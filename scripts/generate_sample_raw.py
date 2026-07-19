"""
Generate a messy raw extract modeled on Ontario Health public ED reporting.

Schema mirrors the CSV export from:
https://hqontario.ca/System-Performance/Time-Spent-in-Emergency-Departments

Values are synthetic demo data calibrated to published provincial averages
(approx. 1.8–2.2 hrs physician assessment; LOS targets 4h / 8h / 8h).
Replace data/raw/ed_wait_times_export.csv with a live Ontario Health export
when you have one — the pipeline accepts the same column layout.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

HOSPITALS = [
    # (canonical, messy variants, region, peergroup)
    ("Toronto General Hospital", ["Toronto General Hospital", "UHN - Toronto General", "TORONTO GENERAL", "Toronto General Hosp."], "Toronto", "Teaching"),
    ("Sunnybrook Health Sciences Centre", ["Sunnybrook Health Sciences Centre", "Sunnybrook HSC", "SUNNYBROOK"], "Toronto", "Teaching"),
    ("St. Michael's Hospital", ["St. Michael's Hospital", "St Michaels Hospital", "Unity Health - St. Michael's"], "Toronto", "Teaching"),
    ("Ottawa Hospital - Civic Campus", ["Ottawa Hospital - Civic Campus", "The Ottawa Hospital Civic", "TOH Civic"], "East", "Teaching"),
    ("Hamilton Health Sciences - General", ["Hamilton Health Sciences - General", "HHS General Site", "Hamilton General"], "West", "Teaching"),
    ("London Health Sciences Centre - Victoria", ["London Health Sciences Centre - Victoria", "LHSC Victoria", "London Victoria Hospital"], "West", "Teaching"),
    ("Kingston Health Sciences Centre", ["Kingston Health Sciences Centre", "KHSC", "Kingston General Hospital"], "East", "Teaching"),
    ("Trillium Health Partners - Mississauga", ["Trillium Health Partners - Mississauga", "THP Mississauga", "Mississauga Hospital"], "Central", "Large Community"),
    ("William Osler Health System - Brampton Civic", ["William Osler Health System - Brampton Civic", "Osler Brampton Civic", "Brampton Civic Hospital"], "Central", "Large Community"),
    ("Markham Stouffville Hospital", ["Markham Stouffville Hospital", "Oak Valley Health - Markham", "Markham Stouffville"], "Central", "Large Community"),
    ("Scarborough Health Network - General", ["Scarborough Health Network - General", "SHN General", "Scarborough General"], "Toronto", "Large Community"),
    ("North York General Hospital", ["North York General Hospital", "NYGH", "North York General"], "Toronto", "Large Community"),
    ("Grand River Hospital", ["Grand River Hospital", "GRH Kitchener", "Grand River Hosp"], "West", "Large Community"),
    ("Thunder Bay Regional Health Sciences Centre", ["Thunder Bay Regional Health Sciences Centre", "TBRHSC", "Thunder Bay Regional"], "North", "Teaching"),
    ("Health Sciences North", ["Health Sciences North", "HSN Sudbury", "Sudbury Regional Hospital"], "North", "Teaching"),
    ("Lakeridge Health - Oshawa", ["Lakeridge Health - Oshawa", "Lakeridge Oshawa", "Oshawa General"], "Central", "Large Community"),
    ("Windsor Regional Hospital - Ouellette", ["Windsor Regional Hospital - Ouellette", "WRH Ouellette", "Windsor Ouellette Campus"], "West", "Large Community"),
    ("Peterborough Regional Health Centre", ["Peterborough Regional Health Centre", "PRHC", "Peterborough Regional"], "East", "Large Community"),
    ("Royal Victoria Regional Health Centre", ["Royal Victoria Regional Health Centre", "RVH Barrie", "Royal Victoria Barrie"], "Central", "Large Community"),
    ("Niagara Health - St. Catharines", ["Niagara Health - St. Catharines", "Niagara Health SCS", "St Catharines General"], "West", "Large Community"),
]

INDICATORS = [
    # (code, target_hours, base_avg, volume_base)
    ("WT_PHYS_ASSESS", 2.0, 2.0, 4200),
    ("LOS_LOW_URGENCY", 4.0, 4.8, 2800),
    ("LOS_HIGH_URGENCY", 8.0, 6.5, 1900),
    ("LOS_ADMITTED", 8.0, 14.2, 900),
]

# Jul 2024 – Jul 2026 (through present reporting month)
PERIODS = []
for y, months in [
    (2024, range(7, 13)),
    (2025, range(1, 13)),
    (2026, range(1, 8)),  # Jan–Jul 2026
]:
    for m in months:
        PERIODS.append(f"{y}{m:02d}")


def _messy_period(period: str, rng: random.Random) -> str:
    y, m = int(period[:4]), int(period[4:])
    style = rng.choice(["yyyymm", "iso", "slash", "text"])
    if style == "yyyymm":
        return period
    if style == "iso":
        return f"{y}-{m:02d}-01"
    if style == "slash":
        return f"{m}/{y}"
    return f"{y}-{m:02d}"


def _pct_within_target(avg: float, target: float, rng: random.Random) -> float | str:
    # Rough logistic-ish mapping from avg vs target → % within target
    ratio = avg / target
    pct = max(25.0, min(95.0, 100.0 - (ratio - 0.7) * 55.0 + rng.uniform(-4, 4)))
    if rng.random() < 0.04:
        return ""  # null
    if rng.random() < 0.03:
        return f"{pct:.1f}%"  # string with %
    return round(pct, 1)


def build_rows(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []

    for hospital, variants, region, peer in HOSPITALS:
        for period in PERIODS:
            for code, target, base_avg, vol_base in INDICATORS:
                # Seasonal bump in winter
                month = int(period[4:])
                season = 1.12 if month in (12, 1, 2) else (0.95 if month in (6, 7, 8) else 1.0)
                peer_factor = 1.08 if peer == "Teaching" else 1.0
                region_factor = {"Toronto": 1.1, "Central": 1.05, "West": 1.0, "East": 0.98, "North": 1.02}[region]

                avg = base_avg * season * peer_factor * region_factor * rng.uniform(0.85, 1.2)
                vol = int(vol_base * season * rng.uniform(0.8, 1.25))

                # Inject quality issues
                if rng.random() < 0.015:
                    avg = -1.0  # invalid
                if rng.random() < 0.02:
                    avg = None
                if rng.random() < 0.01:
                    vol = None

                name = rng.choice(variants)
                pct = _pct_within_target(avg if avg else base_avg, target, rng)

                rows.append(
                    {
                        "Hospital_Name": name,
                        "OH_Region": region if rng.random() > 0.03 else region.upper(),
                        "Peer_Group": peer,
                        "Reporting_Period": _messy_period(period, rng),
                        "Indicator_Code": code if rng.random() > 0.02 else code.lower(),
                        "Avg_Hours": "" if avg is None else round(avg, 2),
                        "Patient_Volume": "" if vol is None else vol,
                        "Pct_Within_Target": pct,
                        "Target_Hours": target,
                    }
                )

    # Duplicate key rows (same hospital/period/indicator, slight value drift)
    dup_src = rows[10], rows[55], rows[120]
    for src in dup_src:
        clone = dict(src)
        if clone["Avg_Hours"] != "":
            clone["Avg_Hours"] = round(float(clone["Avg_Hours"]) + 0.1, 2)
        rows.append(clone)

    rng.shuffle(rows)
    return rows


FIXED_WIDTH_SPEC = [
    ("hospital_name", 45),
    ("oh_region", 12),
    ("peer_group", 18),
    ("reporting_period", 10),
    ("indicator_code", 18),
    ("avg_hours", 8),
    ("patient_volume", 8),
    ("pct_within_target", 8),
    ("target_hours", 6),
]


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_fixed_width(rows: list[dict], path: Path) -> None:
    """Legacy fixed-width extract (stand-in for SAS OUTFILE / PROC EXPORT dump)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    key_map = {
        "hospital_name": "Hospital_Name",
        "oh_region": "OH_Region",
        "peer_group": "Peer_Group",
        "reporting_period": "Reporting_Period",
        "indicator_code": "Indicator_Code",
        "avg_hours": "Avg_Hours",
        "patient_volume": "Patient_Volume",
        "pct_within_target": "Pct_Within_Target",
        "target_hours": "Target_Hours",
    }
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            parts = []
            for field, width in FIXED_WIDTH_SPEC:
                val = str(row.get(key_map[field], ""))
                parts.append(val[:width].ljust(width))
            f.write("".join(parts) + "\n")


def main() -> None:
    rows = build_rows()
    csv_path = RAW_DIR / "ed_wait_times_export.csv"
    fw_path = RAW_DIR / "ed_wait_times_legacy.dat"
    write_csv(rows, csv_path)
    write_fixed_width(rows, fw_path)
    print(f"Wrote {len(rows)} rows → {csv_path}")
    print(f"Wrote fixed-width extract → {fw_path}")


if __name__ == "__main__":
    main()
