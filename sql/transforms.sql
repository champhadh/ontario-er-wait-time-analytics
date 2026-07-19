-- Ontario ER Wait-Time Analytics
-- Transformations applied after Python staging load.
-- Run order: dim_hospital → dim_period → dim_indicator → fact_ed_wait → mart_hospital_month

DROP TABLE IF EXISTS dim_hospital;
CREATE TABLE dim_hospital AS
SELECT
    hospital_key,
    hospital_name,
    oh_region,
    peer_group
FROM (
    SELECT
        hospital_key,
        hospital_name,
        oh_region,
        peer_group,
        ROW_NUMBER() OVER (
            PARTITION BY hospital_key
            ORDER BY hospital_name
        ) AS rn
    FROM stg_ed_wait_times
) ranked
WHERE rn = 1;

DROP TABLE IF EXISTS dim_period;
CREATE TABLE dim_period AS
SELECT DISTINCT
    reporting_period,
    period_date,
    CAST(strftime('%Y', period_date) AS INTEGER) AS report_year,
    CAST(strftime('%m', period_date) AS INTEGER) AS report_month,
    strftime('%Y-%m', period_date) AS year_month
FROM stg_ed_wait_times
WHERE period_date IS NOT NULL;

DROP TABLE IF EXISTS dim_indicator;
CREATE TABLE dim_indicator AS
SELECT DISTINCT
    indicator_code,
    indicator_label,
    target_hours
FROM stg_ed_wait_times;

-- Deduplicate natural key (keep highest volume / most complete submission)
DROP TABLE IF EXISTS fact_ed_wait;
CREATE TABLE fact_ed_wait AS
SELECT
    hospital_key,
    hospital_name,
    oh_region,
    peer_group,
    reporting_period,
    period_date,
    indicator_code,
    indicator_label,
    avg_hours,
    patient_volume,
    pct_within_target,
    target_hours,
    CASE
        WHEN avg_hours IS NOT NULL AND target_hours IS NOT NULL AND avg_hours > target_hours
        THEN 1 ELSE 0
    END AS over_target_flag
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY hospital_key, reporting_period, indicator_code
            ORDER BY COALESCE(patient_volume, 0) DESC, avg_hours DESC
        ) AS rn
    FROM stg_ed_wait_times
    WHERE period_date IS NOT NULL
      AND indicator_code IS NOT NULL
      AND hospital_key IS NOT NULL
) deduped
WHERE rn = 1;

-- Wide mart for Power BI: one row per hospital × month with key measures
DROP TABLE IF EXISTS mart_hospital_month;
CREATE TABLE mart_hospital_month AS
SELECT
    hospital_key,
    hospital_name,
    oh_region,
    peer_group,
    reporting_period,
    period_date,
    MAX(CASE WHEN indicator_code = 'WT_PHYS_ASSESS' THEN avg_hours END) AS avg_wait_physician_hrs,
    MAX(CASE WHEN indicator_code = 'LOS_LOW_URGENCY' THEN avg_hours END) AS avg_los_low_urgency_hrs,
    MAX(CASE WHEN indicator_code = 'LOS_HIGH_URGENCY' THEN avg_hours END) AS avg_los_high_urgency_hrs,
    MAX(CASE WHEN indicator_code = 'LOS_ADMITTED' THEN avg_hours END) AS avg_los_admitted_hrs,
    MAX(CASE WHEN indicator_code = 'WT_PHYS_ASSESS' THEN patient_volume END) AS volume_physician_assess,
    MAX(CASE WHEN indicator_code = 'LOS_LOW_URGENCY' THEN patient_volume END) AS volume_low_urgency,
    MAX(CASE WHEN indicator_code = 'LOS_HIGH_URGENCY' THEN patient_volume END) AS volume_high_urgency,
    MAX(CASE WHEN indicator_code = 'LOS_ADMITTED' THEN patient_volume END) AS volume_admitted,
    MAX(CASE WHEN indicator_code = 'LOS_LOW_URGENCY' THEN pct_within_target END) AS pct_within_target_low,
    MAX(CASE WHEN indicator_code = 'LOS_HIGH_URGENCY' THEN pct_within_target END) AS pct_within_target_high,
    MAX(CASE WHEN indicator_code = 'LOS_ADMITTED' THEN pct_within_target END) AS pct_within_target_admitted
FROM fact_ed_wait
GROUP BY
    hospital_key,
    hospital_name,
    oh_region,
    peer_group,
    reporting_period,
    period_date;
