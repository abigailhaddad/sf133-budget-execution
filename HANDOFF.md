# SF-133 Budget Execution: Operator Guide

For whoever runs this next. It assumes you can run a command and read its output, not that you write Python.

## What it is

The SF-133 for every federal account, month by month, FY2018 to FY2026 (3,060,954 rows in the main table).
OMB posts it as 29 Excel workbooks per fiscal year on MAX.gov. This repo turns the workbooks into three
tables, checks them against the source, and publishes them to Hugging Face in one commit.

**It can refresh on its own, but that is switched off.** A weekly GitHub Action, `refresh.yml`, checks OMB's
pages, downloads only the workbooks that changed, rebuilds them into the published tables, checks the
result and publishes one Hugging Face commit. It stays idle until two things are set, and one of them is a
decision about MAX.gov's robots.txt: see "Automatic refresh" below. Until then, someone downloads the new
workbooks and runs the scripts by hand. OMB updates the workbooks during the year, so a keeper might do it
once a year, after September data, or more often.

## Where things live

| What | Where |
|---|---|
| The data | `abigailhaddad/sf133-budget-execution` on Hugging Face: `sf133_lines` (3,060,954 rows), `sf133_accounts` (77,771), `sf133_workbooks` (261) |
| The dataset card (the README shown on Hugging Face) | Written from `dataset_card/README.template.md` and the tables by `make_card.py`. `publish_to_hf.py` uploads it with the data |
| This code | https://github.com/abigailhaddad/sf133-budget-execution |
| A website to browse it | https://sf133-budget-execution.abigailhaddad.com, a Cloudflare Pages project named `sf133-budget-execution` |
| Where the site comes from | A separate repo, `dataset-explorer`, config `configs/sf133.json`, built with `python3 scripts/build_sites.py sf133-budget-execution` into `dist-sites/sf133-budget-execution/`. **That repo is on one machine only; it has not been pushed to GitHub.** Get a copy from the previous owner |
| The check outputs from the published build | `evidence/` |

The site reads the data from Hugging Face when the page loads, so a data refresh does not need a site
redeploy. Redeploy the site only when its own files or config change.

## Automatic refresh

**What it does, every Monday at 09:17 UTC.** For the current fiscal year, the one before it and the next one
(and two older years on the first Monday of the month) it asks OMB's page for that year, one request each,
6 seconds apart. Each page says "last updated on <date>" and every workbook link carries a version number that
goes up when OMB replaces the file. A workbook is "changed" if it is new, if its version differs from the one
saved last time, or, on the first run, if the page's date is later than the OMB stamp in our data. Only those
workbooks are downloaded, one at a time. They replace their rows in the published lines table; every other row
stays exactly as published (the code proves that: untouched years must match to the cent or nothing is
published). The accounts and workbooks tables and the card are rebuilt from the result, the replaced workbooks are
checked against their source (row counts, the workbook's own "Agency Total" sheet, a spot check of 100+ rows), and
one commit goes to Hugging Face. The saved versions live in the dataset at `state/source_state.json`, in the
same commit as the data, so state and data can never disagree. If nothing changed it exits green; if the versions
it saw differ from the saved ones, it uploads only that small file.

**It is off, on purpose.** MAX.gov's robots.txt reads `User-agent: * / Disallow: /`: no automated access to
any part of the site. The data is public and OMB posts it for downloading, but a scheduled job is a robot.
I found this on 2026-11-06 and made three requests to MAX.gov in total (robots.txt and two fiscal-year pages) before
stopping. The workflow therefore skips, with a notice, until **both** of these exist:

| What | Where | Why |
|---|---|---|
| Secret `HF_TOKEN` | repository Settings, Secrets and variables, Actions | write access to the dataset |
| Variable `SF133_OVERRIDE_ROBOTS` = `yes` | same page, Variables tab | the owner's decision to set robots.txt aside |

The scripts check the variable too, so running them by hand also needs `SF133_OVERRIDE_ROBOTS=yes`. Your options,
in the order I would try them: ask OMB's MAX.gov team whether a weekly check of 3 pages is acceptable or whether
there is a feed; or decide yourself that it is, since the load is a few requests a week and every request stops at
the first block; or keep refreshing by hand. Do not change the User-Agent or add retries around a block.

**Scope.** Only workbooks named `FY<year>_SF133_MONTHLY_<agency>.xlsx` are matched file by file. That is FY2025 and
FY2026 now, and will be every future year. FY2018, FY2023 and FY2024 were built from files named by number; a newer
OMB page for those years only produces a warning in the run summary, and you rebuild them by hand.

**The first run will re-download FY2025.** OMB's FY2025 page says "last updated 2025-12-11", and the published FY2025
data carries the stamp 2025-12-03. The first run cannot tell whether that is a real revision, so it downloads the 29
FY2025 workbooks (183 MB) and rebuilds the year. On my laptop, rehearsing with the same workbooks already on disk, the
rebuild took 70 seconds and peaked at 2.5 GB of memory, and the verify step took 143 seconds and peaked at 1.1 GB. A
GitHub runner has 7 GB of memory and 14 GB of disk, so it should fit, but I have not run it there. The rehearsal
reproduced the published FY2025 rows and accounts exactly (374,711 and 9,219), and every check passed. FY2026's page date
(2026-10-21) matches our data and needs nothing.

**First manual run (do this before trusting the schedule).**
1. Set `HF_TOKEN`. Leave `SF133_OVERRIDE_ROBOTS` unset and run the workflow by hand (Actions, Refresh SF-133, Run
   workflow). It should skip with the two notices. That proves the gate.
2. Set `SF133_OVERRIDE_ROBOTS` to `yes` and run it again. Watch the "Ask OMB what changed" step: it makes 3 requests
   and should list 29 FY2025 workbooks. If a step answers 403 or 429, stop; GitHub's servers may be refused where a
   laptop is not (see below).
3. Read the run summary. The rebuild guard and the verify step must pass before the publish step runs.
4. Open the dataset's commit history: one commit, "Refresh: replaced 29 workbook(s) in FY2025".

**If GitHub's servers cannot reach MAX.gov** I could not test that from here. The fallback is to run the same scripts
on any machine (the commands are in the README) with `HF_TOKEN` set.

**What a red run means.** `check_updates.py` exit 1: the page layout is not what the code expects. Exit 2: the
server blocked us; wait a day. Exit 3: the robots gate. `download_changed.py` exit 1: a workbook would not download
or lacks the "Raw Data" and "TAFS detail" sheets. `rebuild_changed.py` exit 1: the guard refused (an untouched year
moved, or a changed year lost more than 2% of its rows); the message names which. `verify_changed.py` exit 1: a
replaced workbook does not match its source. None of these publishes anything.

## Refreshing the data by hand

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

5. **The card writes itself.** `publish_to_hf.py` builds the card from `dataset_card/README.template.md` and the
   tables (`make_card.py`): the as-of table, the per-year totals, the row counts, the gift-account count. Edit the
   template for wording. Two paragraphs are history and stay as typed: what the first build checked, and the
   comparison with the apportionment site (FY2025).

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

- **The dataset id.** `publish_to_hf.py` and `fetch_published.py` take it from `SF133_HF_REPO` (default
  `abigailhaddad/sf133-budget-execution`). Set the variable or change the default. The refresh workflow needs
  your own `HF_TOKEN` secret and, if you switch it on, the `SF133_OVERRIDE_ROBOTS` variable (see Automatic refresh). The dataset card, the
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
