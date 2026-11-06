"""Tie the Raw Data sheet to the workbook's own 'Agency Total' pivot sheet.
For each (agency, line number, month column): sum of Raw Data vs the pivot cell."""
import sys, warnings
from pathlib import Path
import pandas as pd, numpy as np
warnings.filterwarnings("ignore")

def pivot_agency_total(f, single_agency=None):
    d = pd.read_excel(f, sheet_name="Agency Total", header=None)
    has_agency_level = any(str(d.iat[i, 0]).strip() == "AGENCY" for i in range(0, 12))
    # header row = the row whose cells start with 'Sum of'
    hr = next(i for i in range(0, 30) if d.iloc[i].astype(str).str.startswith("Sum of").any())
    cols = {j: str(d.iat[hr, j])[len("Sum of "):] for j in range(d.shape[1]) if str(d.iat[hr, j]).startswith("Sum of ")}
    # find the Line No column
    lr = hr - 1
    line_col = next(j for j in range(d.shape[1]) if str(d.iat[lr, j]).strip().lower() == "line no")
    rows = []; agency = None if has_agency_level else single_agency; fin = None; cur = None
    for i in range(hr + 1, len(d)):
        a = d.iat[i, 0]
        ln = d.iat[i, line_col]
        b = d.iat[i, 1]
        desc_col = line_col + 2
        if pd.isna(ln) and pd.notna(d.iat[i, desc_col]) and cur is not None:
            ln = cur          # pivot prints Line No once; repeated Cat B rows leave it blank
        elif pd.notna(ln):
            cur = ln
        else:
            cur = None
        if (not has_agency_level) and isinstance(a, str) and "ACCOUNTS" in a and pd.isna(ln):
            fin = a.strip(); continue
        if has_agency_level and isinstance(a, str) and a.strip() and pd.isna(ln):
            agency = a.strip(); fin = None
            if agency.lower().startswith("grand total"): break
            continue
        if has_agency_level and isinstance(b, str) and b.strip() and pd.isna(ln):
            fin = b.strip(); continue
        if pd.notna(ln) and agency:
            try: ln = int(float(ln))
            except Exception: continue
            for j, name in cols.items():
                v = d.iat[i, j]
                rows.append((agency, fin, ln, name, v))
    p = pd.DataFrame(rows, columns=["agency", "fin", "lineno", "col", "pivot"])
    p["pivot"] = pd.to_numeric(p["pivot"], errors="coerce")
    # lines such as 2002/2102 repeat once per Category B activity in the pivot; sum them
    p = p.groupby(["agency", "fin", "lineno", "col"], as_index=False)["pivot"].sum(min_count=1)
    return p

def raw_sums(f):
    r = pd.read_excel(f, sheet_name="Raw Data")
    amt = [c for c in r.columns if c.startswith("AMT") and c != "AGEUP"]
    r["LINENO"] = pd.to_numeric(r["LINENO"], errors="coerce")
    r = r[r["LINENO"].notna()]
    g = r.groupby(["AGENCY", "CRED_IND", "LINENO"], as_index=False)[amt].sum(min_count=1)
    m = g.melt(id_vars=["AGENCY", "CRED_IND", "LINENO"], var_name="col", value_name="raw")
    m = m.rename(columns={"AGENCY": "agency", "CRED_IND": "fin", "LINENO": "lineno"})
    m["fin"] = m["fin"].astype(str).str.strip()
    m["lineno"] = m["lineno"].astype(int)
    m["agency"] = m["agency"].astype(str).str.strip()
    return m, r

def tie(f):
    m, r = raw_sums(f)
    one = r["AGENCY"].astype(str).str.strip().unique()
    p = pivot_agency_total(f, single_agency=one[0] if len(one) == 1 else None)
    j = p.merge(m, on=["agency", "fin", "lineno", "col"], how="outer", indicator=True)
    both = j[j["_merge"] == "both"].copy()
    both["pivot0"] = both["pivot"].fillna(0); both["raw0"] = both["raw"].fillna(0)
    both["diff"] = (both["pivot0"] - both["raw0"]).abs()
    bad = both[both["diff"] > 0.5]
    return dict(file=Path(f).name, pivot_cells=len(p), raw_cells=len(m), compared=len(both),
                mismatches=len(bad), only_pivot=int((j["_merge"] == "left_only").sum()),
                only_raw=int((j["_merge"] == "right_only").sum()),
                only_raw_nonzero=int(((j["_merge"] == "right_only") & (j["raw"].fillna(0).abs() > 0.5)).sum()),
                n_agencies_raw=r["AGENCY"].nunique(), n_agencies_pivot=p["agency"].nunique()), bad, j

if __name__ == "__main__":
    for f in sys.argv[1:]:
        s, bad, j = tie(f)
        print(s)
        if len(bad): print(bad.sort_values("diff", ascending=False).head(5).to_string())
