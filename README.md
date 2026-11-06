# sf133-budget-execution

The SF-133 (Report on Budget Execution and Budgetary Resources) for every federal account, month by
month, FY2018 to FY2026. OMB posts it as 29 Excel workbooks per fiscal year on MAX.gov. This repo reads
the workbooks' `Raw Data` sheets into one table, checks it against the source, and publishes it.

- Dataset: https://huggingface.co/datasets/abigailhaddad/sf133-budget-execution
- Browse it: https://sf133-budget-execution.abigailhaddad.com
- Dataset card: written from `dataset_card/README.template.md` and the tables by `make_card.py`
- Operator guide: [HANDOFF.md](HANDOFF.md). Earlier mistakes to watch for: [docs/HISTORY.md](docs/HISTORY.md)

A weekly GitHub Action (`refresh.yml`) checks OMB's pages and refreshes the data without anyone running a script. It needs the repository variable `SF133_OVERRIDE_ROBOTS` set to `yes`, because MAX.gov's robots.txt disallows automated access. See [HANDOFF.md](HANDOFF.md). The manual route below always works.

## Refresh automatically

```bash
python3 fetch_published.py --out pub            # the published tables, from Hugging Face
python3 check_updates.py --pub pub --out changes.json     # one page request per fiscal year
python3 download_changed.py --changes changes.json --raw raw_changed    # only what changed, one at a time
python3 rebuild_changed.py --pub pub --raw raw_changed --changes changes.json --out build
python3 verify_changed.py --lines build/sf133_lines.parquet --raw raw_changed --changes changes.json
python3 publish_to_hf.py --upload               # one commit; builds the card, includes the saved state
```

`check_updates.py` and `download_changed.py` refuse to run while robots.txt disallows automated access,
unless `SF133_OVERRIDE_ROBOTS=yes` is set. Only workbooks named like OMB's `FY<year>_SF133_MONTHLY_<agency>.xlsx`
are refreshed this way. The tests run with `python3 -m pytest -q tests` and need no network.

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
has no such folder and has to download the workbooks from MAX.gov, one page per fiscal year at
`https://portal.max.gov/portal/document/SF133/Budget/FY%20<year>%20-%20SF%20133%20Reports%20on%20Budget%20Execution%20and%20Budgetary%20Resources.html`.
Copy the link of any workbook on that page and drop the file name for the base URL that `download_workbooks.sh`
takes. The script waits 3 seconds between files, uses an honest User-Agent and stops on a 403 or 429. It has
only been tested on FY2026. Do it over a few days. OMB updates the workbooks
during the year, so `source_updated` in the data is the as-of date.

`evidence/` holds the outputs of the checks from the published build.

## License

Code: MIT. The data are U.S. government works in the public domain. This is an unofficial copy.
