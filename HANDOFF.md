# SF-133 Budget Execution: Operator Guide

For whoever runs this next. It assumes you can run a command and read its output, not that you write Python.

## What it is

The SF-133 for every federal account, month by month, FY2018 to FY2026 (3,060,954 rows in the main table).
OMB posts it as 29 Excel workbooks per fiscal year on MAX.gov. This repo turns the workbooks into three
tables, checks them against the source, and publishes them to Hugging Face in one commit.

**Nothing refreshes on its own.** There is no scheduled job and no GitHub Action. Someone downloads the
new workbooks and runs the scripts. OMB updates the workbooks during the year, so a keeper might do it
once a year, after September data, or more often.

## Where things live

| What | Where |
|---|---|
| The data | `abigailhaddad/sf133-budget-execution` on Hugging Face: `sf133_lines` (3,060,954 rows), `sf133_accounts` (77,771), `sf133_workbooks` (261) |
| The dataset card (the README shown on Hugging Face) | `dataset_card/README.md`. `publish_to_hf.py` uploads it with the data |
| This code | https://github.com/abigailhaddad/sf133-budget-execution |
| A website to browse it | https://sf133-budget-execution.abigailhaddad.com, a Cloudflare Pages project named `sf133-budget-execution` |
| Where the site comes from | A separate repo, `dataset-explorer`, config `configs/sf133.json`, built with `python3 scripts/build_sites.py sf133-budget-execution` into `dist-sites/sf133-budget-execution/`. **That repo is on one machine only; it has not been pushed to GitHub.** Get a copy from the previous owner |
| The check outputs from the published build | `evidence/` |

The site reads the data from Hugging Face when the page loads, so a data refresh does not need a site
redeploy. Redeploy the site only when its own files or config change.

## Refreshing the data

1. **Get the workbooks.** MAX.gov has one page per fiscal year, at
   `https://portal.max.gov/portal/document/SF133/Budget/FY%20<year>%20-%20SF%20133%20Reports%20on%20Budget%20Execution%20and%20Budgetary%20Resources.html`.
   (`apportion/sf133_urls.json` in the earlier repo lists these pages for 2016 to 2025. I did not re-check them.)
   Open the year's page, copy the link of any workbook, and drop the file name from the end. What is left
   is the base URL. Then:

   ```bash
   export SF133_RAW=~/sf133_raw
   bash download_workbooks.sh 2027 "https://portal.max.gov/portal/document/SF133/Budget/attachments/<number>"
   ```

   It asks for one file every 3 seconds with a plain, honest User-Agent, skips files it already has, and
   stops if the server answers 403 or 429. If it stops, wait a day. The file names follow the FY2026
   pattern (`FY2026_SF133_MONTHLY_<agency>.xlsx`). **I have not tested the script on any year but 2026,
   and I have not run it against MAX.gov at all in this repo's final form.** If a download returns a
   404, compare the real names on the year's page with the list in the script.

   **Earlier years are not in this repo.** The first build read FY2018 to FY2025 from
   `~/Documents/repos/apportion/raw_data`, a folder on the previous owner's machine (2.8 GB, years 2016
   to 2025, with duplicates). FY2026 was downloaded into `scratch/raw2026` (184 MB, 29 files). A new
   owner has to download every year again, 2018 to 2025 into `$SF133_RAW/<year>/` and 2026 into
   `scratch/raw2026`. That is a lot of requests: do it over a few days, politely.

2. **Run the chain, in this order** (also in the README):

   ```bash
   python3 inventory.py                 # lists the workbooks; writes inventory_workbooks.csv
   python3 rawsummary.py                # one summary row per workbook; writes raw_data_sheet_summary.csv
   python3 duphash.py                   # hashes of workbooks that look like duplicates
   python3 rawsummary2026.py            # the same for scratch/raw2026
   python3 select_workbooks.py          # one workbook per agency per year; writes workbooks.csv
   python3 build_sf133.py --raw "$SF133_RAW" --raw2026 scratch/raw2026 --workbooks workbooks.csv --out build
   python3 make_tables.py               # the accounts and workbooks tables
   python3 verify_build.py              # must say 0 mismatches before you publish
   python3 tieout_batch.py 2018 2022 2025 2026   # name the years you changed
   python3 -m pytest -q tests
   ```

   A new fiscal year needs its folder at `$SF133_RAW/<year>/` and the same chain. FY2026 is the one year
   with its own folder and summary script, because it was added after the first build. If FY2026 also
   sits in `$SF133_RAW/2026/`, `select_workbooks.py` would count it twice: keep it in one place.

   **Size and time.** The finished build is 117 MB (`sf133_lines.parquet` 112 MB). The builder uses 4
   processes. I did not time the chain. Plan on several minutes for the build and longer for the checks,
   and about 3 GB of free disk if you keep all the workbooks.

3. **Check before publishing.** `verify_build.py` counts rows per workbook against the source, looks for
   repeated keys, and compares 104 random and edge-case rows, every field and month, against the cells in
   the workbook with a different reader. In the published build: 3,060,954 of 3,060,954 rows, 0 duplicate
   row ids, 0 mismatches in 2,080 fields. `tieout_batch.py` compares each workbook's own "Agency Total"
   sheet with the Raw Data sheet. If either reports a problem, do not publish.

4. **Publish.** `python3 publish_to_hf.py` is a dry run: it checks the build and says whether the dataset
   exists. Add `--upload` for one commit that replaces the three tables and the card. It needs a Hugging
   Face token with write access to the dataset's account, in `HF_TOKEN` or from `hf auth login`. The commit
   message names the first and last fiscal year in the build.

5. **Update the card.** The per-year counts in `dataset_card/README.md` (rows, the accounts left out of
   the apportionment site's totals) are written by hand. Recount them from the new build before you upload.

## Known issues

These are in the dataset card too. Keep them there.

- **No October.** No workbook reports October. The column is empty in every year.
- **FY2019** has no January or February in any workbook. FY2026's GSA workbook has none either.
- **Accounts with no line 2490.** OMB reports no unobligated balance for some fully obligated accounts, so
  `unobligated_balance_end_of_period` is null for them (525 accounts in FY2025). They still have a line
  2500. The apportionment site drops them from its totals, which is why its totals are smaller.
- **Financing accounts** are in the table. Summing `total_budgetary_resources` over every row includes
  them (about $721.7B in FY2025).
- **Line 2500 is total budgetary resources**, not budget authority (line 1900).
- **Repeated keys on purpose.** Category B lines carry several rows per account and line. They add up to
  the report line.
- **Left out:** the DEFC workbooks (a separate cut that repeats accounts), exact duplicate downloads
  (141 in FY2018 to FY2022), FY2016 and FY2017, and the names and emails of the people who filed each
  Category B row.
- **The gift-account flag** is a title match (gift, donation, bequest). It is not a judgment.
- **Not checked:** the figures against OMB's published PDFs, and the sign of every amount beyond the sample.

## What went wrong in the earlier version

An earlier build of the same workbooks, in the `apportion` repo, had four errors. This build was made to
avoid them, and they are the first thing to look for if a number looks off:

1. Every row in a workbook got the first agency name in it, so 14% to 27% of rows per year carried the wrong
   agency. This build labels each row from its own agency, bureau and account columns.
2. It read every workbook in the folder, including 141 exact duplicate downloads and the DEFC workbooks,
   so each account appeared about four times in FY2018 to FY2022. `select_workbooks.py` keeps one per
   agency per year.
3. Allocation accounts were added into their parent accounts. TAFS and allocation code are keys here.
4. A column called budget authority was really line 2500. Here line 1900 and line 2500 have separate names.

The fix and the numbers are in https://github.com/abigailhaddad/apportionment/pull/2.

## If someone else takes it over

- **The dataset id.** `publish_to_hf.py` takes it from `SF133_HF_REPO` (default
  `abigailhaddad/sf133-budget-execution`). Set the variable or change the default. The dataset card, the
  README and the site's config also name it.
- **Names in the card and README:** the GitHub repo, the explorer site, and the link to the apportionment
  analysis page, `https://apportionment-analysis.pages.dev`.
- **The site.** In `dataset-explorer`, `scripts/build_sites.py` has an entry for this site (slug, title,
  Hugging Face dataset, repo) and `configs/sf133.json` names the dataset's files. Change them, rebuild, and
  deploy `dist-sites/sf133-budget-execution/` to your own Cloudflare Pages project:
  `npx wrangler pages deploy dist-sites/sf133-budget-execution --project-name <yours> --branch main`.
  It needs a Cloudflare API token with Pages edit permission and your account id. Add the custom address in
  Pages, then one CNAME record in your DNS.
- **The adoption page** card for this dataset names the repo, dataset and site.

## When something breaks

- **The download stops at a 403 or 429.** Do not retry that day.
- **A 404 on a workbook.** The name differs from the pattern. Compare with the year's page.
- **`build_sf133.py` fails or the row counts differ.** OMB changed a sheet or column. The month columns are
  named `AMT_<MONTH>` for single months and `AMT1` to `AMT4` for quarter ends. Look at what changed in the
  workbook's Raw Data sheet before you change the parser.
- **`verify_build.py` reports mismatches.** Do not publish. Fix the build or find out why the source differs.
