#!/usr/bin/env python3
"""
Ontario ER Wait-Time Analytics — one-command refresh.

Raw file → clean staging → SQL transforms → SQLite → DQ report → Power BI CSV

Usage (from repo root, with venv active):
    python etl/run_pipeline.py
    python etl/run_pipeline.py --source fixed-width
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "etl"))

from convert_fixed_width import convert as convert_fixed_width  # noqa: E402

RAW_CSV = ROOT / "data" / "raw" / "ed_wait_times_export.csv"
RAW_DAT = ROOT / "data" / "raw" / "ed_wait_times_legacy.dat"
FW_CSV = ROOT / "data" / "raw" / "ed_wait_times_from_fixed_width.csv"
DB_PATH = ROOT / "data" / "db" / "ontario_er.db"
CLEAN_CSV = ROOT / "data" / "processed" / "ed_wait_times_clean.csv"
MART_CSV = ROOT / "data" / "processed" / "mart_hospital_month.csv"
DQ_REPORT = ROOT / "reports" / "data_quality_report.txt"
TRANSFORMS_SQL = ROOT / "sql" / "transforms.sql"
QUALITY_SQL = ROOT / "sql" / "quality_checks.sql"

INDICATOR_LABELS = {
    "WT_PHYS_ASSESS": "Wait time to first physician assessment",
    "LOS_LOW_URGENCY": "Length of stay — low urgency, not admitted",
    "LOS_HIGH_URGENCY": "Length of stay — high urgency, not admitted",
    "LOS_ADMITTED": "Length of stay — admitted patients",
}

# Collapse common hospital-name variants into a stable key
HOSPITAL_ALIASES = {
    "uhn - toronto general": "toronto general hospital",
    "toronto general": "toronto general hospital",
    "toronto general hosp.": "toronto general hospital",
    "sunnybrook hsc": "sunnybrook health sciences centre",
    "sunnybrook": "sunnybrook health sciences centre",
    "st michaels hospital": "st. michael's hospital",
    "unity health - st. michael's": "st. michael's hospital",
    "the ottawa hospital civic": "ottawa hospital - civic campus",
    "toh civic": "ottawa hospital - civic campus",
    "hhs general site": "hamilton health sciences - general",
    "hamilton general": "hamilton health sciences - general",
    "lhsc victoria": "london health sciences centre - victoria",
    "london victoria hospital": "london health sciences centre - victoria",
    "khsc": "kingston health sciences centre",
    "kingston general hospital": "kingston health sciences centre",
    "thp mississauga": "trillium health partners - mississauga",
    "mississauga hospital": "trillium health partners - mississauga",
    "osler brampton civic": "william osler health system - brampton civic",
    "brampton civic hospital": "william osler health system - brampton civic",
    "oak valley health - markham": "markham stouffville hospital",
    "markham stouffville": "markham stouffville hospital",
    "shn general": "scarborough health network - general",
    "scarborough general": "scarborough health network - general",
    "nygh": "north york general hospital",
    "north york general": "north york general hospital",
    "grh kitchener": "grand river hospital",
    "grand river hosp": "grand river hospital",
    "tbrhsc": "thunder bay regional health sciences centre",
    "thunder bay regional": "thunder bay regional health sciences centre",
    "hsn sudbury": "health sciences north",
    "sudbury regional hospital": "health sciences north",
    "lakeridge oshawa": "lakeridge health - oshawa",
    "oshawa general": "lakeridge health - oshawa",
    "wrh ouellette": "windsor regional hospital - ouellette",
    "windsor ouellette campus": "windsor regional hospital - ouellette",
    "prhc": "peterborough regional health centre",
    "peterborough regional": "peterborough regional health centre",
    "rvh barrie": "royal victoria regional health centre",
    "royal victoria barrie": "royal victoria regional health centre",
    "niagara health scs": "niagara health - st. catharines",
    "st catharines general": "niagara health - st. catharines",
}


def normalize_hospital(name: str) -> tuple[str, str]:
    raw = (name or "").strip()
    key = re.sub(r"\s+", " ", raw.lower())
    canonical = HOSPITAL_ALIASES.get(key, key)
    display = canonical.title().replace("Of ", "of ").replace("And ", "and ")
    # Keep known punctuation
    display = display.replace("St. Michael'S", "St. Michael's")
    display = display.replace("St Michaels", "St. Michael's")
    return canonical, display


def parse_period(value) -> pd.Timestamp | pd.NaT:
    if pd.isna(value) or value == "":
        return pd.NaT
    s = str(value).strip()
    # YYYYMM
    if re.fullmatch(r"\d{6}", s):
        return pd.to_datetime(s + "01", format="%Y%m%d", errors="coerce")
    # YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return pd.to_datetime(s + "-01", format="%Y-%m-%d", errors="coerce")
    # M/YYYY
    if re.fullmatch(r"\d{1,2}/\d{4}", s):
        return pd.to_datetime(s, format="%m/%Y", errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def parse_pct(value) -> float | None:
    if pd.isna(value) or value == "":
        return None
    s = str(value).strip().replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    colmap = {c: c.strip() for c in df.columns}
    df = df.rename(columns=colmap)

    required = [
        "Hospital_Name",
        "OH_Region",
        "Peer_Group",
        "Reporting_Period",
        "Indicator_Code",
        "Avg_Hours",
        "Patient_Volume",
        "Pct_Within_Target",
        "Target_Hours",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Raw file missing columns: {missing}")

    out = pd.DataFrame()
    keys_names = df["Hospital_Name"].map(normalize_hospital)
    out["hospital_key"] = keys_names.map(lambda x: x[0])
    out["hospital_name"] = keys_names.map(lambda x: x[1])
    out["oh_region"] = df["OH_Region"].astype(str).str.strip().str.title()
    out["peer_group"] = df["Peer_Group"].astype(str).str.strip()
    out["reporting_period"] = df["Reporting_Period"].astype(str).str.strip()
    out["period_date"] = df["Reporting_Period"].map(parse_period)
    out["indicator_code"] = df["Indicator_Code"].astype(str).str.strip().str.upper()
    out["indicator_label"] = out["indicator_code"].map(INDICATOR_LABELS)
    out["avg_hours"] = pd.to_numeric(df["Avg_Hours"], errors="coerce")
    out["patient_volume"] = pd.to_numeric(df["Patient_Volume"], errors="coerce")
    out["pct_within_target"] = df["Pct_Within_Target"].map(parse_pct)
    out["target_hours"] = pd.to_numeric(df["Target_Hours"], errors="coerce")

    # Drop junk rows with no hospital
    out = out[out["hospital_key"].str.len() > 0].copy()

    # Null out impossible averages / percents (DQ then confirms clean ranges)
    bad_avg = out["avg_hours"].notna() & ((out["avg_hours"] < 0) | (out["avg_hours"] > 72))
    out.loc[bad_avg, "avg_hours"] = pd.NA
    bad_pct = out["pct_within_target"].notna() & (
        (out["pct_within_target"] < 0) | (out["pct_within_target"] > 100)
    )
    out.loc[bad_pct, "pct_within_target"] = None

    # Stabilize reporting_period to YYYYMM when parseable
    mask = out["period_date"].notna()
    out.loc[mask, "reporting_period"] = out.loc[mask, "period_date"].dt.strftime("%Y%m")

    return out


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script on semicolons, ignoring -- line comments."""
    cleaned_lines = []
    for line in sql.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        # Drop trailing inline comments
        if "--" in line:
            line = line[: line.index("--")]
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def run_sql_script(engine, path: Path) -> None:
    statements = _split_sql(path.read_text(encoding="utf-8"))
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def run_quality_checks(engine) -> list[tuple[str, str, str]]:
    statements = _split_sql(QUALITY_SQL.read_text(encoding="utf-8"))
    results = []
    with engine.connect() as conn:
        for stmt in statements:
            row = conn.execute(text(stmt)).fetchone()
            if row:
                results.append((row[0], row[1], row[2]))
    return results


def write_dq_report(results: list[tuple[str, str, str]], elapsed: float) -> bool:
    DQ_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Ontario ER Wait-Time Analytics — Data Quality Report",
        f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Pipeline runtime: {elapsed:.2f}s",
        "",
        f"{'CHECK':<32} {'STATUS':<6} DETAIL",
        "-" * 80,
    ]
    all_pass = True
    for name, status, detail in results:
        if status != "PASS":
            all_pass = False
        lines.append(f"{name:<32} {status:<6} {detail}")
    lines.append("-" * 80)
    lines.append("OVERALL: " + ("PASS" if all_pass else "FAIL"))
    report = "\n".join(lines) + "\n"
    DQ_REPORT.write_text(report, encoding="utf-8")
    print(report)
    return all_pass


def export_for_powerbi(engine) -> None:
    CLEAN_CSV.parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        fact = pd.read_sql("SELECT * FROM fact_ed_wait ORDER BY period_date, hospital_name, indicator_code", conn)
        mart = pd.read_sql("SELECT * FROM mart_hospital_month ORDER BY period_date, hospital_name", conn)
    fact.to_csv(CLEAN_CSV, index=False)
    mart.to_csv(MART_CSV, index=False)
    print(f"Exported {len(fact)} fact rows → {CLEAN_CSV.relative_to(ROOT)}")
    print(f"Exported {len(mart)} mart rows → {MART_CSV.relative_to(ROOT)}")


def resolve_source(source: str) -> Path:
    if source == "csv":
        if not RAW_CSV.exists():
            raise FileNotFoundError(
                f"Missing {RAW_CSV}. Run: python scripts/generate_sample_raw.py"
            )
        return RAW_CSV
    if source == "fixed-width":
        if not RAW_DAT.exists():
            raise FileNotFoundError(f"Missing {RAW_DAT}")
        n = convert_fixed_width(RAW_DAT, FW_CSV)
        print(f"Converted fixed-width extract ({n} rows) → {FW_CSV.name}")
        return FW_CSV
    raise ValueError(f"Unknown source: {source}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Ontario ER wait-time analytics DB")
    parser.add_argument(
        "--source",
        choices=["csv", "fixed-width"],
        default="csv",
        help="Raw input: messy CSV export (default) or legacy fixed-width .dat",
    )
    args = parser.parse_args()

    t0 = time.perf_counter()
    print("=== Ontario ER Wait-Time Pipeline ===")
    raw_path = resolve_source(args.source)
    print(f"Reading raw file: {raw_path.relative_to(ROOT)}")

    raw = pd.read_csv(raw_path, dtype=str, keep_default_na=False)
    print(f"Raw rows: {len(raw)}")

    staged = clean_frame(raw)
    print(f"Staged rows after Python clean: {len(staged)}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    engine = create_engine(f"sqlite:///{DB_PATH}")

    staged.to_sql("stg_ed_wait_times", engine, index=False, if_exists="replace")
    print("Loaded staging table: stg_ed_wait_times")

    run_sql_script(engine, TRANSFORMS_SQL)
    print("Applied SQL transforms (dims, fact_ed_wait, mart_hospital_month)")

    results = run_quality_checks(engine)
    elapsed = time.perf_counter() - t0
    ok = write_dq_report(results, elapsed)

    export_for_powerbi(engine)

    print(f"SQLite database: {DB_PATH.relative_to(ROOT)}")
    print(f"Done in {elapsed:.2f}s — DQ {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
