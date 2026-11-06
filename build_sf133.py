#!/usr/bin/env python3
"""Build the SF-133 tables from the MAX.gov agency workbooks.

One row per Raw Data row: TAFS x line number (x Category B activity for lines 2002, 2102 and
similar). Amounts are fiscal-year-to-date, in dollars. Agency, bureau and account labels come
from the row itself. The apportion pipeline instead gave a whole workbook the first agency name
it found; see FINDINGS.md.

    python3 build_sf133.py --raw ~/Documents/repos/apportion/raw_data --raw2026 scratch/raw2026 --out build

Outputs, in --out:
    sf133_lines.parquet     the table
    sf133_accounts.parquet  one row per fiscal year x TAFS: labels and codes
    build_report.json       row counts per workbook, units, which months have data
"""
import argparse
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

MONTHS = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
# The Raw Data sheet names single months AMT_<MON>, but quarter ends arrive as AMT1..AMT4.
MONTH_COL = {
    "Oct": "AMT_OCT", "Nov": "AMT_NOV", "Dec": "AMT1",
    "Jan": "AMT_JAN", "Feb": "AMT_FEB", "Mar": "AMT2",
    "Apr": "AMT_APR", "May": "AMT_MAY", "Jun": "AMT3",
    "Jul": "AMT_JUL", "Aug": "AMT_AUG", "Sep": "AMT4",
}
TEXT_COLS = {
    "AGENCY": "agency", "BUREAU": "bureau",
    "OMB_ACCOUNT": "omb_account", "TAFS": "tafs",
    "TRAG": "agency_code", "TRACCT": "account_code", "ALLOC": "allocation_code",
    "FY1": "begin_year", "FY2": "end_year", "STAT": "availability",
    "CRED_IND": "financing", "LINENO": "line_no", "LINE_DESC": "line_desc",
    "SECTION": "section", "SECTION_NO": "section_no", "LINE_TYPE": "line_type",
    "CAT_B": "cat_b", "PGM_CAT": "program_category", "LAST_UPDATED": "source_updated",
}


def clean(s):
    """Excel text arrives with _x000D_ and stray line breaks inside TAFS strings."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    t = str(s).replace("_x000D_\n", " ").replace("_x000D_", " ").replace("\r", " ").replace("\n", " ")
    return " ".join(t.split()) or None


def units_of(path):
    """The TAFS detail sheet header says '(Dollars)' or '(Thousands)'."""
    head = pd.read_excel(path, sheet_name="TAFS detail", header=None, nrows=8)
    text = " ".join(str(v).lower() for v in head.values.ravel() if pd.notna(v))
    if "thousand" in text:
        return 1000, "thousands"
    if "dollar" in text:
        return 1, "dollars"
    raise ValueError(f"cannot tell units for {path.name}")


def parse_workbook(path, fiscal_year):
    mult, units = units_of(path)
    raw = pd.read_excel(path, sheet_name="Raw Data", dtype={"TRAG": str, "TRACCT": str, "ALLOC": str,
                                                              "FY1": str, "FY2": str})
    out = pd.DataFrame(index=raw.index)
    for src, dest in TEXT_COLS.items():
        out[dest] = raw[src].map(clean) if src in raw.columns else None
    out["line_no"] = pd.to_numeric(raw["LINENO"], errors="coerce").astype("Int64")
    out["source_row"] = raw.index + 2        # Excel row number in the Raw Data sheet (header is row 1)
    out = out[out["line_no"].notna()].copy()
    present = []
    for m in MONTHS:
        col = MONTH_COL[m]
        if col in raw.columns:
            vals = pd.to_numeric(raw.loc[out.index, col], errors="coerce")
        else:
            vals = pd.Series(np.nan, index=out.index)
        out[m.lower()] = vals * mult
    # A month nobody reported is null for the whole workbook, not zero.
    for m in MONTHS:
        c = m.lower()
        if not (out[c].fillna(0) != 0).any():
            out[c] = np.nan
        else:
            present.append(m)
    out["fiscal_year"] = int(fiscal_year)
    out["source_units"] = units
    out["source_file"] = path.name
    return out, {"file": path.name, "rows": int(len(out)), "units": units,
                 "agencies": int(out["agency"].nunique()), "months_with_data": present}


def _job(args):
    return parse_workbook(*args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--raw2026")
    ap.add_argument("--workbooks", help="CSV from select_workbooks.py: fiscal_year,path")
    ap.add_argument("--out", default="build")
    a = ap.parse_args()
    out_dir = Path(a.out)
    out_dir.mkdir(exist_ok=True)

    plan = pd.read_csv(a.workbooks, dtype=str)
    frames, report = [], []
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    jobs = [(Path(r.path), r.fiscal_year) for r in plan.itertuples()]
    with ProcessPoolExecutor(4, mp_context=mp.get_context("fork")) as ex:
        results = list(ex.map(_job, jobs))
    for (path, fy), (df, rep) in zip(jobs, results):
        frames.append(df)
        report.append({"fiscal_year": int(fy), **rep})
        print(f"FY{fy} {rep['file'][:60]:60s} {rep['rows']:>8,}  {rep['units']}", flush=True)
    lines = pd.concat(frames, ignore_index=True)
    lines.to_parquet(out_dir / "sf133_lines.parquet", index=False, compression="zstd")
    json.dump(report, open(out_dir / "build_report.json", "w"), indent=1)
    print(f"{len(lines):,} rows")


if __name__ == "__main__":
    main()
