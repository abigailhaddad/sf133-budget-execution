import os
import warnings, sys
from pathlib import Path
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import pandas as pd, numpy as np
warnings.filterwarnings("ignore")
RAW = Path(os.environ.get("SF133_RAW", Path.home() / "Documents/repos/apportion/raw_data"))

def digest(args):
    year, file = args
    r = pd.read_excel(RAW/year/file, sheet_name="Raw Data")
    cols = [c for c in r.columns if not c.startswith("Column")]
    r = r[cols]
    h = int(pd.util.hash_pandas_object(r.astype(str), index=False).astype("uint64").sum() % (2**63))
    amt = [c for c in cols if c.startswith("AMT") and c != "AGEUP"]
    s = float(np.nansum(np.abs(r[amt].apply(pd.to_numeric, errors="coerce").values)))
    return dict(year=year, file=file, rows=len(r), content_hash=h, abs_sum=round(s, 2))

if __name__ == "__main__":
    d = pd.read_csv("raw_data_sheet_summary.csv")
    d["key"] = d.year.astype(str)+"|"+d.first_agency.astype(str)+"|"+d.rows.astype(str)+"|"+d.n_tafs.astype(str)
    dup = d[d.groupby("key").file.transform("count") > 1]
    todo = [(str(r.year), r.file) for r in dup.itertuples()]
    with ProcessPoolExecutor(4, mp_context=mp.get_context("fork")) as ex:
        out = list(ex.map(digest, todo))
    o = pd.DataFrame(out); o = o.merge(dup[["year","file","key"]].assign(year=lambda x: x.year.astype(str)), on=["year","file"])
    o.to_csv("duplicate_workbooks_hashes.csv", index=False)
    print("done", len(o))
