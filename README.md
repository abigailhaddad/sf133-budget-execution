# sf133-budget-execution

The SF-133 (Report on Budget Execution and Budgetary Resources) for every federal account, month by
month, FY2018 to FY2026. OMB posts it as 29 Excel workbooks per fiscal year on MAX.gov. This repo reads
the workbooks' `Raw Data` sheets into one table, checks it against the source, and publishes it.

- Dataset: https://huggingface.co/datasets/abigailhaddad/sf133-budget-execution
- Browse it: https://sf133-budget-execution.abigailhaddad.com
- Dataset card: `dataset_card/README.md`
- Operator guide: [HANDOFF.md](HANDOFF.md)

Nothing here refreshes on its own. A keeper downloads the new workbooks and runs the scripts below.

## Rebuild

```bash
python3 -m pip install pandas openpyxl pyarrow duckdb huggingface_hub pytest
export SF133_RAW=~/sf133_raw             # a folder with one subfolder per fiscal year: 2018, 2019, ...
bash download_workbooks.sh 2025 <attachments-base-url>   # once per year; see HANDOFF.md for the base URL
python3 inventory.py                     # which workbooks exist and which have a Raw Data sheet
python3 rawsummary.py                    # one summary row per workbook
python3 duphash.py                       # content hashes for workbooks that look like duplicates
python3 rawsummary2026.py                # FY2026 lives in scratch/raw2026 and has its own summary
python3 select_workbooks.py              # one workbook per agency per year; drops DEFC and exact duplicates
python3 build_sf133.py --raw "$SF133_RAW" --raw2026 scratch/raw2026 --workbooks workbooks.csv --out build
python3 make_tables.py
python3 verify_build.py                  # row counts, duplicates, spot check against the source cells
python3 tieout_batch.py 2018 2022 2025 2026   # each workbook's own pivot sheet vs the Raw Data sheet
python3 -m pytest -q tests
python3 publish_to_hf.py                 # dry run; add --upload to commit
```

`SF133_RAW` defaults to `~/Documents/repos/apportion/raw_data`, where this was first built. A new owner
has no such folder and has to download the workbooks (HANDOFF.md says how). OMB updates the workbooks
during the year, so `source_updated` in the data is the as-of date.

`evidence/` holds the outputs of the checks from the published build.

## License

Code: MIT. The data are U.S. government works in the public domain. This is an unofficial copy.
