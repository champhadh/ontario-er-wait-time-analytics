# SAS → Python / SQL conversion

The snippet in `legacy_extract.sas` is a typical hospital analytics handoff: fixed-width `INFILE`, sort/dedupe, target flag. Mapped line-for-line:

| SAS | Python / SQL |
|---|---|
| `INFILE` + positional `INPUT` | `etl/convert_fixed_width.py` (`SPEC` slices) |
| `PROC SORT` + `FIRST.indicator_code` | `sql/transforms.sql` → `ROW_NUMBER() ... PARTITION BY hospital_key, reporting_period, indicator_code` |
| `over_target_flag = (avg_hours > target_hours)` | same expression in `fact_ed_wait` |
| Ad-hoc monthly refresh | `python etl/run_pipeline.py --source fixed-width` |

Run the fixed-width path:

```bash
python etl/run_pipeline.py --source fixed-width
```
