#!/usr/bin/env python3
"""Choose the workbooks to build from: one per agency workbook per fiscal year.

Drops (a) DEFC workbooks, a separate cut by Disaster Emergency Funding Code that repeats accounts
already in the agency workbooks, and (b) exact duplicate downloads (same agency, same rows; the
content hashes in duplicate_workbooks_hashes.csv show the Raw Data sheets are identical).
"""
import os
import sys
from pathlib import Path
import pandas as pd

RAW = Path(os.environ.get("SF133_RAW", Path.home() / "Documents/repos/apportion/raw_data"))
RAW26 = Path("scratch/raw2026")

def is_defc(path):
    cols = pd.read_excel(path, sheet_name="Raw Data", nrows=0).columns
    return "DEFC" in cols

d = pd.read_csv("raw_data_sheet_summary.csv")
d = d[(d.year >= 2018)].copy()
d["key"] = d.year.astype(str) + "|" + d.first_agency.astype(str) + "|" + d.rows.astype(str) + "|" + d.n_tafs.astype(str)
d["path"] = [str(RAW / str(r.year) / r.file) for r in d.itertuples()]
d["defc"] = [is_defc(p) for p in d.path]
keep, dropped = [], []
for key, g in d[~d.defc].groupby("key"):
    g = g.sort_values("file", key=lambda s: s.str.contains("MONTHLY").map({True: 0, False: 1}))
    keep.append(g.iloc[0]); dropped += [(r.year, r.file, g.iloc[0].file) for r in g.iloc[1:].itertuples()]
sel = pd.DataFrame(keep)[["year", "file", "path", "rows", "n_agency", "first_agency"]].rename(columns={"year": "fiscal_year"})
s26 = pd.read_csv("raw_data_sheet_summary_2026.csv")
add = pd.DataFrame({"fiscal_year": 2026, "file": s26.file, "path": [str(RAW26 / f) for f in s26.file],
                    "rows": s26.rows, "n_agency": s26.n_agency, "first_agency": s26.first_agency})
sel = pd.concat([sel, add], ignore_index=True).sort_values(["fiscal_year", "file"])
sel.to_csv("workbooks.csv", index=False)
pd.DataFrame(dropped, columns=["year", "dropped_duplicate", "kept"]).to_csv("dropped_duplicate_workbooks.csv", index=False)
pd.DataFrame([(r.year, r.file) for r in d[d.defc].itertuples()], columns=["year", "dropped_defc"]).to_csv("dropped_defc_workbooks.csv", index=False)
print(sel.groupby("fiscal_year").agg(workbooks=("file", "count"), rows=("rows", "sum"), agency_labels=("n_agency", "sum")).to_string())
print("duplicates dropped:", len(dropped), "| DEFC dropped:", int(d.defc.sum()))
