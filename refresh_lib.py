"""The logic behind the automatic refresh. Nothing here touches the network.

The scripts that do (check_updates.py, download_changed.py) pass what they fetched into these
functions, which is what the tests exercise.

How a change is detected. OMB's page for each fiscal year is plain HTML with one link per workbook.
The page says "last updated on YYYY-MM-DD", and each workbook link carries a version number
(data-linked-resource-version) that goes up when OMB replaces the file. One request per fiscal year
is enough to see what changed.
"""
import datetime as dt
import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

PAGE_BASE = "https://portal.max.gov/portal/document/SF133/Budget/"
PAGE_NAME = "FY%%20%d%%20-%%20SF%%20133%%20Reports%%20on%%20Budget%%20Execution%%20and%%20Budgetary%%20Resources.html"
MONTHLY_NAME = re.compile(r"^FY(\d{4})_SF133_MONTHLY_.+\.xlsx$")
UPDATED = re.compile(r"last updated on (\d{4}-\d{2}-\d{2})", re.I)
MONTH_ORDER = ["oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep"]
LINE_COLS = ["fiscal_year", "source_file", "source_row"]


def page_url(fy):
    return PAGE_BASE + PAGE_NAME % int(fy)


def current_fiscal_year(today=None):
    """The federal fiscal year runs October to September and is named for the year it ends in."""
    today = today or dt.date.today()
    return today.year + (1 if today.month >= 10 else 0)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            a = dict(attrs)
            if a.get("href"):
                self.links.append(a)


def parse_fy_page(page_html, fy, url=None):
    """What the fiscal-year page says: its 'last updated' date and its monthly workbooks.

    Returns {"fiscal_year", "last_updated" (or None), "files": {name: {"href", "version", "resource_id"}}}.
    Only the agency workbooks named FY<year>_SF133_MONTHLY_<agency>.xlsx are kept.
    """
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page_html, flags=re.S)
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)))
    m = UPDATED.search(text)
    p = _Links()
    p.feed(page_html)
    files = {}
    for a in p.links:
        href = html.unescape(a["href"])
        name = href.rsplit("/", 1)[-1]
        mm = MONTHLY_NAME.match(name)
        if not mm or int(mm.group(1)) != int(fy):
            continue
        files[name] = {
            "href": urljoin(url, href) if url else href,
            "version": _int(a.get("data-linked-resource-version")),
            "resource_id": a.get("data-linked-resource-id"),
        }
    return {"fiscal_year": int(fy), "last_updated": m.group(1) if m else None, "files": files}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def plan_changes(page, state_year, published_files, published_max_updated):
    """Which workbooks of one fiscal year need downloading.

    page                   parse_fy_page() output
    state_year             the saved state for this year: {"page_last_updated", "files": {name: {"version"}}}, or None
    published_files        source_file names already in the published workbooks table for this year
    published_max_updated  the latest source_updated date in the published data for this year, or None

    A file is changed when
      - it is new (not in the published data),
      - its version differs from the saved one, or
      - nothing is saved for it yet and the page's 'last updated' date is later than the data's.
    The last rule is the first run's baseline: with no saved versions, the page date against the
    data's own OMB stamp says whether we are already current.
    """
    changed, warnings = [], []
    saved = (state_year or {}).get("files", {})
    for name, f in sorted(page["files"].items()):
        reason = None
        if name not in published_files:
            reason = "new workbook"
        elif name in saved:
            if f["version"] is not None and f["version"] != saved[name].get("version"):
                reason = f"version {saved[name].get('version')} -> {f['version']}"
        else:
            lu = page.get("last_updated")
            if lu and published_max_updated and lu > published_max_updated:
                reason = f"page updated {lu}, data stamped {published_max_updated}"
        if reason:
            changed.append({"fiscal_year": page["fiscal_year"], "name": name, "href": f["href"], "reason": reason})
    for name in sorted(set(published_files) - set(page["files"])):
        warnings.append(f"FY{page['fiscal_year']}: published workbook {name} is not listed on OMB's page")
    return changed, warnings


def next_state(old_state, pages, checked_at):
    """The state to save after a successful refresh: what each checked page said just now."""
    years = dict((old_state or {}).get("years", {}))
    for fy, page in pages.items():
        years[str(fy)] = {
            "page_last_updated": page["last_updated"],
            "files": {n: {"version": f["version"], "resource_id": f["resource_id"]} for n, f in page["files"].items()},
        }
    return {"schema": 1, "checked_at": checked_at, "years": years}


def years_to_check(today=None, include_past=0):
    """The current fiscal year, the one before it (OMB revises it for months after it ends), the next
    one (its page appears in the autumn), and optionally some older years."""
    cur = current_fiscal_year(today)
    ys = [cur + 1, cur, cur - 1]
    ys += [cur - 1 - i for i in range(1, include_past + 1)]
    return ys


def latest_month(row_counts_by_month):
    """The last month in fiscal order that has any value. row_counts_by_month: {'oct': n, ...}."""
    got = None
    for m in MONTH_ORDER:
        if row_counts_by_month.get(m):
            got = m
    return got


def guard(published, new, changed_years, max_shrink=0.02):
    """Reasons not to publish. Empty list means go.

    published / new   {"lines": {fy: rows}, "accounts": {fy: (rows, cents)}, "fingerprints": {fy: tuple}}
    changed_years     fiscal years that had workbooks replaced or added

    Years nobody touched must come through identical. A changed year may grow or shrink a little;
    one that loses more than max_shrink of its rows is not published.
    """
    problems = []
    n_acc = lambda d, fy: (d["accounts"].get(fy) or (0,))[0]
    for fy in published["lines"]:
        if fy not in new["lines"]:
            problems.append(f"FY{fy} is missing from the new lines table")
    for fy, n in published["lines"].items():
        if fy in changed_years or fy not in new["lines"]:
            continue
        if new["lines"][fy] != n:
            problems.append(f"FY{fy} was not touched but its lines went from {n:,} to {new['lines'][fy]:,}")
        if published["fingerprints"].get(fy) != new["fingerprints"].get(fy):
            problems.append(f"FY{fy} was not touched but its values changed")
        if published["accounts"].get(fy) != new["accounts"].get(fy):
            problems.append(f"FY{fy} was not touched but its accounts changed "
                            f"({published['accounts'].get(fy)} -> {new['accounts'].get(fy)})")
    for fy in changed_years:
        old = published["lines"].get(fy)
        if old and new["lines"].get(fy, 0) < old * (1 - max_shrink):
            problems.append(f"FY{fy} shrank from {old:,} to {new['lines'].get(fy, 0):,} lines "
                            f"(more than {max_shrink:.0%})")
        olda = n_acc(published, fy)
        if olda and n_acc(new, fy) < olda * (1 - max_shrink):
            problems.append(f"FY{fy} accounts shrank from {olda:,} to {n_acc(new, fy):,}")
    tot_old, tot_new = sum(published["lines"].values()), sum(new["lines"].values())
    if tot_new < tot_old * (1 - max_shrink):
        problems.append(f"total lines shrank from {tot_old:,} to {tot_new:,}")
    return problems
