# Power BI dashboard build (15–20 minutes)

## Connect

1. Open Power BI Desktop → **Get data** → **Text/CSV**.
2. Select `data/processed/mart_hospital_month.csv` (refreshed by the pipeline).
3. Optional: also load `ed_wait_times_clean.csv` if you want indicator-level drill-through.

*SQLite option:* Get data → ODBC / SQLite connector → `data/db/ontario_er.db` → table `mart_hospital_month`.

## Visuals (build these four)

| # | Visual | Fields | Notes |
|---|---|---|---|
| 1 | Clustered bar | Axis: `hospital_name`, Value: measure **Avg Wait to Physician (hrs)** | Sort descending — longest waits first |
| 2 | Line chart | Axis: `period_date`, Value: **Avg Wait to Physician (hrs)**, Legend: `oh_region` | Trend over time by OH region |
| 3 | Card + KPI | **Avg % Within Target (Low Urgency)** | Format as % |
| 4 | Card | **% Hospital-Months Over Low-Urgency Target** | Format as % — talk track for “over target” |

Optional fifth: matrix of `hospital_name` × latest month with `avg_los_admitted_hrs` and measure **Admitted LOS vs Target (hrs)**.

## Measures

Copy from `powerbi/measures.dax` into a new measure table (or onto `mart_hospital_month`).

Talking points in interviews:
- **Avg Wait to Physician** is volume-weighted so large EDs don’t get drowned out by tiny sites.
- **% Hospital-Months Over Low-Urgency Target** is a simple over-target rate against Ontario’s 4-hour low-urgency LOS target.

## Screenshot for README

Export a page view → save as `docs/dashboard_preview.png` (a matplotlib stand-in is already generated for the repo until you swap in the real Power BI export).
