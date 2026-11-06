#!/usr/bin/env python3
"""Ask OMB's fiscal-year pages what changed since the last refresh. Writes changes.json.

    python3 check_updates.py --pub pub --out changes.json [--include-past 1] [--years 2026 2025]

One page request per fiscal year, with a pause between requests (SF133_PAUSE, default 6 s). Reads the
published tables in --pub (see fetch_published.py) to know what is already in the dataset, and the saved
state there (state/source_state.json) to know which workbook versions were seen last time.

Exit codes: 0 fine (changes or none), 1 the page layout is not what the code expects, 2 the server
blocked us, 3 robots.txt disallows automated access and the owner has not overridden it.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

import maxgov
import refresh_lib as lib


def load_published(pub):
    """(workbook names per fiscal year, latest source_updated per fiscal year, saved state or None)."""
    pub = Path(pub)
    wb = pd.read_parquet(pub / "sf133_workbooks.parquet")
    names = {int(fy): set(g["source_file"]) for fy, g in wb.groupby("fiscal_year")}
    con = duckdb.connect()
    rows = con.execute(f"select fiscal_year, max(source_updated) from read_parquet('{pub / 'sf133_lines.parquet'}') "
                       "group by 1").fetchall()
    stamped = {int(fy): d for fy, d in rows}
    sp = pub / "source_state.json"
    state = json.loads(sp.read_text()) if sp.exists() else None
    return names, stamped, state


def check(years, names, stamped, state, fetch_page, today=None, sleep=None):
    """Compare each year's page with what we have. fetch_page(fy) -> (status, html text).

    Returns {"changed": [...], "warnings": [...], "pages": {fy: parsed page}, "problems": [...]}."""
    changed, warnings, pages, problems = [], [], {}, []
    cur = lib.current_fiscal_year(today)
    for i, fy in enumerate(years):
        if i and sleep:
            sleep()
        status, text = fetch_page(fy)
        if status == 404:
            warnings.append(f"FY{fy}: no page yet (404)")
            continue
        if status != 200:
            problems.append(f"FY{fy}: the page answered {status}")
            continue
        page = lib.parse_fy_page(text, fy, url=lib.page_url(fy))
        if not page["files"] and not page["last_updated"]:
            # A page with neither the 'last updated' line nor any workbook link has changed shape.
            if fy <= cur:
                problems.append(f"FY{fy}: the page loaded but has no 'last updated' line and no workbook links; "
                                "its layout may have changed")
            else:
                warnings.append(f"FY{fy}: page exists, nothing published on it yet")
            continue
        pages[fy] = page
        # Only years whose published workbooks use OMB's monthly file names can be matched file by file.
        have = names.get(fy, set())
        if have and not all(lib.MONTHLY_NAME.match(n) for n in have):
            lu = page["last_updated"]
            if lu and stamped.get(fy) and lu > stamped[fy]:
                warnings.append(f"FY{fy}: OMB's page says updated {lu}, the data is stamped {stamped[fy]}. "
                                "This year's published workbooks do not use OMB's file names, so it is not "
                                "refreshed automatically. Rebuild it by hand (HANDOFF.md).")
            continue
        ch, w = lib.plan_changes(page, (state or {}).get("years", {}).get(str(fy)), have, stamped.get(fy))
        changed += ch
        warnings += w
    return {"changed": changed, "warnings": warnings, "pages": pages, "problems": problems}


def real_fetch_page(fy):
    status, _, body = maxgov.get(lib.page_url(fy))
    return status, body.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", default="pub")
    ap.add_argument("--out", default="changes.json")
    ap.add_argument("--years", nargs="*", type=int)
    ap.add_argument("--include-past", type=int, default=0, help="also check this many older years")
    a = ap.parse_args()

    names, stamped, state = load_published(a.pub)
    years = a.years or lib.years_to_check(include_past=a.include_past)
    try:
        maxgov.require_permission(lib.page_url(years[0]))
        res = check(years, names, stamped, state, real_fetch_page, sleep=maxgov.pause)
    except maxgov.RobotsDisallow as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        sys.exit(3)
    except maxgov.Blocked as e:
        print(f"STOPPED: {e}. Do not retry from this address today.", file=sys.stderr)
        sys.exit(2)

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {
        "checked_at": now,
        "years_checked": years,
        "pages": {str(fy): {"last_updated": p["last_updated"], "files": len(p["files"])} for fy, p in res["pages"].items()},
        "changed": res["changed"],
        "warnings": res["warnings"],
        "problems": res["problems"],
        "state_next": lib.next_state(state, res["pages"], now),
    }
    Path(a.out).write_text(json.dumps(out, indent=1))
    for w in res["warnings"]:
        print("WARNING:", w)
    for p in res["problems"]:
        print("PROBLEM:", p, file=sys.stderr)
    print(f"{len(res['changed'])} workbook(s) to download across {len({c['fiscal_year'] for c in res['changed']})} year(s)")
    for c in res["changed"]:
        print(f"  FY{c['fiscal_year']} {c['name']}: {c['reason']}")
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"changed={'true' if res['changed'] else 'false'}\n")
            f.write(f"n_changed={len(res['changed'])}\n")
    if res["problems"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
