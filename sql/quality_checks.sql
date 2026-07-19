-- Data quality checks for fact_ed_wait / mart_hospital_month
-- Each query returns: check_name, status (PASS/FAIL), detail

SELECT
    'row_count_fact' AS check_name,
    CASE WHEN cnt >= 100 THEN 'PASS' ELSE 'FAIL' END AS status,
    'fact_ed_wait rows=' || cnt AS detail
FROM (SELECT COUNT(*) AS cnt FROM fact_ed_wait);

SELECT
    'row_count_mart' AS check_name,
    CASE WHEN cnt >= 50 THEN 'PASS' ELSE 'FAIL' END AS status,
    'mart_hospital_month rows=' || cnt AS detail
FROM (SELECT COUNT(*) AS cnt FROM mart_hospital_month);

SELECT
    'null_avg_hours_threshold' AS check_name,
    CASE WHEN null_pct <= 5.0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'null avg_hours pct=' || ROUND(null_pct, 2) AS detail
FROM (
    SELECT
        100.0 * SUM(CASE WHEN avg_hours IS NULL THEN 1 ELSE 0 END) / COUNT(*) AS null_pct
    FROM fact_ed_wait
);

SELECT
    'avg_hours_in_range' AS check_name,
    CASE WHEN bad = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'out_of_range rows (not between 0 and 72)=' || bad AS detail
FROM (
    SELECT COUNT(*) AS bad
    FROM fact_ed_wait
    WHERE avg_hours IS NOT NULL
      AND (avg_hours < 0 OR avg_hours > 72)
);

SELECT
    'no_duplicate_keys' AS check_name,
    CASE WHEN dupes = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'duplicate natural keys=' || dupes AS detail
FROM (
    SELECT COUNT(*) AS dupes
    FROM (
        SELECT hospital_key, reporting_period, indicator_code, COUNT(*) AS c
        FROM fact_ed_wait
        GROUP BY hospital_key, reporting_period, indicator_code
        HAVING COUNT(*) > 1
    )
);

SELECT
    'pct_within_target_range' AS check_name,
    CASE WHEN bad = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'pct_within_target outside 0-100=' || bad AS detail
FROM (
    SELECT COUNT(*) AS bad
    FROM fact_ed_wait
    WHERE pct_within_target IS NOT NULL
      AND (pct_within_target < 0 OR pct_within_target > 100)
);

SELECT
    'period_date_coverage' AS check_name,
    CASE WHEN null_periods = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'null period_date rows=' || null_periods AS detail
FROM (
    SELECT COUNT(*) AS null_periods
    FROM fact_ed_wait
    WHERE period_date IS NULL
);

SELECT
    'staging_to_fact_dedupe' AS check_name,
    CASE WHEN stg_cnt >= fact_cnt AND fact_cnt > 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    'stg=' || stg_cnt || ' fact=' || fact_cnt || ' removed=' || (stg_cnt - fact_cnt) AS detail
FROM (
    SELECT
        (SELECT COUNT(*) FROM stg_ed_wait_times) AS stg_cnt,
        (SELECT COUNT(*) FROM fact_ed_wait) AS fact_cnt
);
