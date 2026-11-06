"""One summary row per workbook that has a Raw Data sheet."""
import os
import warnings, sys, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import pandas as pd, openpyxl
warnings.filterwarnings("ignore")
RAW = Path(os.environ.get("SF133_RAW", Path.home() / "Documents/repos/apportion/raw_data"))

def units(f):
    try:
        h = pd.read_excel(f, sheet_name="TAFS detail", header=None, nrows=8)
        t = " ".join(str(v).lower() for v in h.values.ravel() if pd.notna(v))
        return "thousands" if "thousand" in t else ("dollars" if "dollar" in t else "unknown")
    except Exception: return "err"

def one(path):
    f = Path(path)
    try:
        r = pd.read_excel(f, sheet_name="Raw Data")
    except Exception as e:
        return dict(year=f.parent.name, file=f.name, error=str(e)[:80])
    amt = [c for c in r.columns if c.startswith("AMT") and c != "AGEUP"]
    nz = [c for c in amt if pd.to_numeric(r[c], errors="coerce").fillna(0).abs().sum() > 0]
    ag = r["AGENCY"].dropna().astype(str).str.strip() if "AGENCY" in r else pd.Series(dtype=str)
    return dict(year=f.parent.name, file=f.name, rows=len(r), cols=len(r.columns),
        rpt_yr=",".join(sorted(map(str, r["RPT_YR"].dropna().unique())))[:20] if "RPT_YR" in r else "",
        n_agency=ag.nunique(), first_agency=ag.iloc[0] if len(ag) else "",
        agencies=" | ".join(sorted(ag.unique())[:3]),
        n_tafs=r["TAFS"].nunique() if "TAFS" in r else 0,
        last_updated=",".join(sorted(map(str, r["LAST_UPDATED"].dropna().astype(str).str[:10].unique()))[:2]) if "LAST_UPDATED" in r else "",
        amt_cols=",".join(sorted(amt)), nonzero_amt_cols=",".join(sorted(nz)),
        units=units(f), mb=round(f.stat().st_size/1e6,1))

if __name__ == "__main__":
    inv = pd.read_csv("inventory_workbooks.csv")
    paths = [str(RAW/r.year.__str__()/r.file) for r in inv[inv.has_raw_data].itertuples()]
    with ProcessPoolExecutor(4, mp_context=mp.get_context('fork')) as ex:
        rows = list(ex.map(one, paths))
    pd.DataFrame(rows).to_csv("raw_data_sheet_summary.csv", index=False)
    print("done", len(rows))
