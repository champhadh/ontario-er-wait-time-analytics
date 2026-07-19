/* Legacy hospital ED wait-time extract (illustrative)
   Typical Access to Care / NACRS-style monthly rollup dump.
   Converted to Python (etl/convert_fixed_width.py + etl/run_pipeline.py)
   and SQL (sql/transforms.sql) — see sas/CONVERSION.md.
*/

LIBNAME raw '/data/ed_wait';

DATA raw.ed_monthly;
    INFILE '/data/ed_wait/ed_wait_times_legacy.dat'
        LRECL=133 TRUNCOVER;
    INPUT
        hospital_name       $45.
        oh_region           $12.
        peer_group          $18.
        reporting_period    $10.
        indicator_code      $18.
        avg_hours            8.
        patient_volume       8.
        pct_within_target    8.
        target_hours         6.;
RUN;

/* Deduplicate natural key — keep highest volume submission */
PROC SORT DATA=raw.ed_monthly;
    BY hospital_name reporting_period indicator_code DESCENDING patient_volume;
RUN;

DATA raw.ed_monthly_dedup;
    SET raw.ed_monthly;
    BY hospital_name reporting_period indicator_code;
    IF FIRST.indicator_code;
RUN;

/* Flag months over provincial target */
DATA raw.ed_monthly_flags;
    SET raw.ed_monthly_dedup;
    over_target_flag = (avg_hours > target_hours);
RUN;
