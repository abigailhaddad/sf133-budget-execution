#!/usr/bin/env python3
"""Rebuild the tables from the published ones plus the workbooks that changed.

    python3 rebuild_changed.py --pub pub --raw raw_changed --changes changes.json --out build

Reads the published lines, accounts and workbooks tables from --pub, re-reads only the workbooks named in
changes.json, and writes the new tables to --out in the layout publish_to_hf.py expects. Then runs the
guard: years nobody touched must come through identical, and a changed year may not lose more than 2% of
its rows. Exit 1 if the guard objects; nothing is published from here either way.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

import make_tables
import refresh_data as rd
import refresh_lib as lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pub", default="pub")
    ap.add_argument("--raw", default="raw_changed")
    ap.add_argument("--changes", default="changes.json")
    ap.add_argument("--out", default="build")
    ap.add_argument("--max-shrink", type=float, default=0.02)
    a = ap.parse_args()
    pub, out = Path(a.pub), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ch = json.loads(Path(a.changes).read_text())
    changed = ch["changed"]
    if not changed:
        sys.exit("changes.json lists nothing to rebuild")
    t0 = time.time()
    replaced = [(int(c["fiscal_year"]), c["name"]) for c in changed]
    years = {fy for fy, _ in replaced}

    before = rd.summarize(pub / "sf133_lines.parquet", pub / "sf133_accounts.parquet")
    parts, reports, counts = rd.parse_changed(a.raw, changed, out / "parts", pub / "sf133_lines.parquet")
    print(f"parsed {len(parts)} workbook(s), {sum(counts.values()):,} rows, {time.time() - t0:.0f}s", flush=True)

    rd.merge_lines(pub / "sf133_lines.parquet", parts, replaced, out / "sf133_lines.parquet")
    wb = rd.merge_workbooks(pd.read_parquet(pub / "sf133_workbooks.parquet"), reports, replaced)
    wb.to_parquet(out / "sf133_workbooks.parquet", index=False)
    acc, latest = make_tables.build_accounts(out / "sf133_lines.parquet")
    acc.to_parquet(out / "sf133_accounts.parquet", index=False, compression="zstd")
    pd.Series(latest).to_json(out / "latest_month.json")
    rd.write_json(out / "source_state.json", ch["state_next"])
    after = rd.summarize(out / "sf133_lines.parquet", out / "sf133_accounts.parquet")

    problems = lib.guard(before, after, years, a.max_shrink)
    report = {
        "changed_workbooks": [{"fiscal_year": fy, "file": n, "rows": counts[(fy, n)]} for fy, n in replaced],
        "years_changed": sorted(years),
        "lines_before": before["lines"], "lines_after": after["lines"],
        "accounts_before": {k: v[0] for k, v in before["accounts"].items()},
        "accounts_after": {k: v[0] for k, v in after["accounts"].items()},
        "guard_problems": problems, "seconds": round(time.time() - t0),
        "checked_at": ch["checked_at"], "reasons": {f"{c['fiscal_year']}|{c['name']}": c["reason"] for c in changed},
    }
    rd.write_json(out / "refresh_report.json", report)
    for fy in sorted(years):
        print(f"FY{fy}: lines {before['lines'].get(fy, 0):,} -> {after['lines'][fy]:,}; "
              f"accounts {(before['accounts'].get(fy) or (0,))[0]:,} -> {after['accounts'][fy][0]:,}")
    if problems:
        print("GUARD: not safe to publish:\n  " + "\n  ".join(problems), file=sys.stderr)
        sys.exit(1)
    print(f"rebuilt in {time.time() - t0:.0f}s; guard passed")


if __name__ == "__main__":
    main()
