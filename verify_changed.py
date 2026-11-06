#!/usr/bin/env python3
"""Checks on the workbooks a refresh replaced. Writes verify_changed.json; exit 1 if anything is off.

    python3 verify_changed.py --lines build/sf133_lines.parquet --raw raw_changed --changes changes.json

For every replaced workbook:
  1. Row count: the table holds one row per Raw Data row that has a line number.
  2. Tie-out: sums of the Raw Data rows equal the workbook's own 'Agency Total' pivot sheet.
  3. Spot check: random rows and edge cases, every field and month, compared with the source cell,
     read with openpyxl (a different reader than the build uses).
And across the whole table for the changed years:
  4. No line key appears in two workbooks of the same year, and no row id repeats.
"""
import argparse
import json
import multiprocessing as mp
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import duckdb
import pandas as pd

import tieout
import verify_build as vb

warnings.filterwarnings("ignore")


def _raw_rows(path):
    r = pd.read_excel(path, sheet_name="Raw Data", usecols=["LINENO"])
    return int(pd.to_numeric(r["LINENO"], errors="coerce").notna().sum())


def _tie(path):
    try:
        s, bad, _ = tieout.tie(path)
        return {"file": Path(path).name, "compared": s["compared"], "mismatches": s["mismatches"],
                "only_raw_nonzero": s["only_raw_nonzero"], "max_abs_diff": float(bad["diff"].max()) if len(bad) else 0.0}
    except Exception as e:
        return {"file": Path(path).name, "error": f"{type(e).__name__}: {str(e)[:150]}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default="build/sf133_lines.parquet")
    ap.add_argument("--raw", default="raw_changed")
    ap.add_argument("--changes", default="changes.json")
    ap.add_argument("--out", default="verify_changed.json")
    a = ap.parse_args()
    changes = json.loads(Path(a.changes).read_text())["changed"]
    if not changes:
        print("nothing replaced, nothing to verify")
        return
    path_of = {(int(c["fiscal_year"]), c["name"]): str(Path(a.raw) / str(c["fiscal_year"]) / c["name"]) for c in changes}
    years = sorted({fy for fy, _ in path_of})
    con = duckdb.connect()
    pairs = ",".join(f"({fy}, '{n}')" for fy, n in path_of)
    df = con.execute(f"select * from read_parquet('{a.lines}') where (fiscal_year, source_file) in ({pairs})").df()
    report, problems = {"workbooks": len(path_of), "rows": int(len(df))}, []

    # 1. row counts
    per = df.groupby(["fiscal_year", "source_file"]).size().to_dict()
    gaps = []
    for (fy, n), path in path_of.items():
        want, got = _raw_rows(path), int(per.get((fy, n), 0))
        if want != got:
            gaps.append((fy, n, want, got))
    report["row_count_gaps"] = gaps
    problems += [f"FY{fy} {n}: Raw Data has {w:,} rows with a line number, the table has {g:,}" for fy, n, w, g in gaps]

    # 2. tie-out
    with ProcessPoolExecutor(4, mp_context=mp.get_context("fork")) as ex:
        ties = list(ex.map(_tie, path_of.values()))
    report["tieout"] = {"workbooks": len(ties), "cells_compared": sum(t.get("compared", 0) for t in ties),
                        "mismatches": sum(t.get("mismatches", 0) for t in ties),
                        "errors": [t for t in ties if "error" in t]}
    for t in ties:
        if "error" in t:
            problems.append(f"tie-out failed to run on {t['file']}: {t['error']}")
        elif t["mismatches"] or t["compared"] == 0:
            problems.append(f"tie-out: {t['file']} has {t['mismatches']} cells where the pivot and the Raw Data differ "
                            f"({t['compared']} compared)")

    # 3. spot check
    sample = vb.spot_sample(df, None)
    checked, bad = vb.spot_check(sample, path_of)
    report["spot_rows"], report["spot_fields_checked"], report["spot_mismatches"] = int(len(sample)), checked, len(bad)
    report["spot_mismatch_examples"] = [list(map(str, x)) for x in bad[:10]]
    if bad:
        problems.append(f"spot check: {len(bad)} of {checked:,} fields differ from the source cells")

    # 4. duplicates across the changed years
    yl = ",".join(map(str, years))
    key = "fiscal_year, tafs, allocation_code, financing, line_no, line_desc, cat_b"
    x = con.execute(f"""select count(*) from (select 1 from read_parquet('{a.lines}') where fiscal_year in ({yl})
        group by {key} having count(distinct source_file) > 1)""").fetchone()[0]
    y = con.execute(f"""select count(*) from (select 1 from read_parquet('{a.lines}') where fiscal_year in ({yl})
        group by fiscal_year, source_file, source_row having count(*) > 1)""").fetchone()[0]
    report["line_keys_in_more_than_one_workbook"], report["duplicate_row_ids"] = int(x), int(y)
    if x:
        problems.append(f"{x:,} line keys appear in more than one workbook of the same year")
    if y:
        problems.append(f"{y:,} row ids repeat")

    report["problems"] = problems
    Path(a.out).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: v for k, v in report.items() if k != "spot_mismatch_examples"}, indent=1, default=str))
    if problems:
        print("VERIFY FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        sys.exit(1)
    print("verify passed")


if __name__ == "__main__":
    main()
