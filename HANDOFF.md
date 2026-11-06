# Handoff

## What this is
The SF-133 budget execution report for every federal account, month by month, FY2018 to FY2026, from OMB's workbooks on MAX.gov.
- Code: https://github.com/abigailhaddad/sf133-budget-execution
- Data: https://huggingface.co/datasets/abigailhaddad/sf133-budget-execution (columns, units and known limits: see the dataset card)
- Site: https://sf133-budget-execution.abigailhaddad.com (built from https://github.com/abigailhaddad/dataset-explorer, site `sf133-budget-execution`)

## What runs on its own
- `.github/workflows/refresh.yml` runs weekly (you can also start it from the Actions tab). It checks OMB's year pages, downloads only the workbooks that changed, rebuilds those, checks the result and publishes one Hugging Face commit. When nothing changed it ends green. The saved page versions live in the dataset at `state/source_state.json`.
- `.github/workflows/tests.yml` runs the tests on every push and pull request.
- MAX.gov's robots.txt says `Disallow: /`, which disallows automated visits. The owner decided a weekly pass over a few pages is fine, so the repository variable `SF133_OVERRIDE_ROBOTS` is set to `yes`. The run asks for one year page per fiscal year (three most weeks, five on the first Monday of the month), one at a time, and stops at the first 401, 403 or 429. Don't change the User-Agent or add retries around a block.
- **By hand:** FY2018, FY2023 and FY2024. Their workbooks are named by number, so a newer OMB page for them only produces a warning in the run summary. Rebuild them from the README ("Rebuild").

## Secrets and variables
- `HF_TOKEN` (secret): a Hugging Face token with write access to the dataset.
- `SF133_OVERRIDE_ROBOTS` (variable): `yes` allows the weekly check. Without it the run skips with a notice and contacts nobody.

## If you take it over
- Dataset id: `SF133_HF_REPO` (default `abigailhaddad/sf133-budget-execution`) in `publish_to_hf.py` and `fetch_published.py`. To find the other places: `grep -rn abigailhaddad . --exclude-dir=.git --exclude-dir=evidence`. They include the card template, the README and the site config.
- Set your own `HF_TOKEN` and the `SF133_OVERRIDE_ROBOTS` variable, or ask OMB's MAX.gov team about a feed first.
- The site: `scripts/build_sites.py` and `configs/sf133.json` in dataset-explorer name the dataset. That repo's `deploy-sites.yml` deploys it to a Cloudflare Pages project called `sf133-budget-execution`.
- The older years' workbooks are not in this repo. To rebuild FY2018, FY2023 or FY2024 you download them from MAX.gov again (README).

## When it breaks
Open the Actions tab and the "Refresh SF-133" run. A red run publishes nothing. The script that failed tells you why:
- `check_updates.py` exit 3: the robots variable is missing. Exit 2: MAX.gov blocked the run, so wait a day. Exit 1: an OMB page didn't look as expected.
- `download_changed.py` exit 1: a workbook would not download.
- `rebuild_changed.py` exit 1: the guard refused. A year nobody touched changed, or a changed year lost more than 2% of its rows.
- `verify_changed.py` exit 1: a replaced workbook doesn't match its source.

If a number looks wrong, read `docs/HISTORY.md` first.

## Costs
No model is called.
