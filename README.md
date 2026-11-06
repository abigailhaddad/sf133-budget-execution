# sf133-dataset

Builds the SF-133 budget-execution dataset (every federal account, month by month, FY2018 to FY2026) from
the agency workbooks OMB posts on MAX.gov, and publishes it to Hugging Face. The dataset card is
`dataset_card/README.md`.

Staging copy, not yet published. Nothing here has been uploaded.

## Rebuild

```bash
python3 -m pip install pandas openpyxl pyarrow duckdb huggingface_hub pytest
bash download_2026.sh                    # the FY2026 workbooks, from MAX.gov, one at a time
python3 rawsummary.py                    # one summary row per workbook (needs inventory.py first)
python3 select_workbooks.py              # one workbook per agency per year; drops DEFC and exact duplicates
python3 build_sf133.py --raw x --workbooks workbooks.csv --out build
python3 make_tables.py
python3 verify_build.py                  # row counts, duplicates, 104-row spot check against the source cells
python3 -m pytest -q tests
python3 publish_to_hf.py                 # dry run; add --upload to commit
```

`select_workbooks.py` and `inventory.py` read the earlier years' workbooks from
`~/Documents/repos/apportion/raw_data`. For a new fiscal year, download that year's workbooks, point
the scripts at them, and rebuild. OMB updates the workbooks during the year, so the update date in
the data (`source_updated`) is the as-of date.

`tieout.py` and `tieout_batch.py` compare the Raw Data sheet with each workbook's own Agency Total
pivot. `evidence/` holds the outputs of the checks.
