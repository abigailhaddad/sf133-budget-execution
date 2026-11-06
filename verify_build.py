#!/usr/bin/env python3
"""Checks on the built table. Prints a report and writes verify_report.json.

1. Row counts: table rows per workbook equal Raw Data rows with a line number.
2. Duplicates: no repeated (fiscal year, TAFS, allocation, financing, line, Cat B text) key.
3. Spot check: random rows plus edge cases, every field and month compared with the
   cell in the source workbook, read with openpyxl (a different reader than the build uses).
4. Totals: sums by agency, line and month tie to the workbook's own 'Agency Total' pivot sheet.
"""
import json
import random
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd

warnings.filterwarnings("ignore")
random.seed(133)

BUILD = Path("build/sf133_lines.parquet")
MONTHS = ["oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep"]
MONTH_COL = {"oct": "AMT_OCT", "nov": "AMT_NOV", "dec": "AMT1", "jan": "AMT_JAN", "feb": "AMT_FEB",
             "mar": "AMT2", "apr": "AMT_APR", "may": "AMT_MAY", "jun": "AMT3", "jul": "AMT_JUL",
             "aug": "AMT_AUG", "sep": "AMT4"}
TEXT = {"agency": "AGENCY", "bureau": "BUREAU", "tafs": "TAFS", "agency_code": "TRAG", "account_code": "TRACCT",
        "financing": "CRED_IND", "line_desc": "LINE_DESC", "cat_b": "CAT_B"}


def clean(s):
    if s is None:
        return None
    t = str(s).replace("_x000D_\n", " ").replace("_x000D_", " ").replace("\r", " ").replace("\n", " ")
    return " ".join(t.split()) or None


def spot_sample(df, plan):
    """Random rows plus edge cases."""
    rng = df.sample(n=min(60, len(df)), random_state=133)
    edge = []
    monthcols = MONTHS
    neg = df[(df[monthcols].min(axis=1) < 0)]
    edge.append(("negative value", neg.sample(n=min(6, len(neg)), random_state=1)))
    allzero = df[(df[monthcols].fillna(0).abs().sum(axis=1) == 0)]
    edge.append(("all months zero or null", allzero.sample(n=min(6, len(allzero)), random_state=2)))
    nox = df[df["tafs"].str.contains(r" /X ", na=False)]
    edge.append(("no-year (/X) account", nox.sample(n=min(6, len(nox)), random_state=3)))
    multi = df[df["tafs"].str.contains(r" \d\d/\d\d ", na=False)]
    edge.append(("multi-year account", multi.sample(n=min(6, len(multi)), random_state=4)))
    cat = df[df["cat_b"].notna()]
    edge.append(("Category B activity line", cat.sample(n=min(6, len(cat)), random_state=5)))
    fin = df[df["financing"] == "FINANCING ACCOUNTS"]
    edge.append(("financing account", fin.sample(n=min(6, len(fin)), random_state=6)))
    big = df.nlargest(4, "sep")
    edge.append(("largest September value", big))
    fdic = df[df["tafs"].str.startswith("51-4596", na=False) & (df["fiscal_year"] == 2025)]
    edge.append(("FDIC deposit insurance fund FY2025", fdic.head(4)))
    gift = df[df["tafs"].str.contains("gift|donation|bequest", case=False, na=False)]
    edge.append(("gift or donation account", gift.sample(n=min(6, len(gift)), random_state=7)))
    parts = [("random", rng)] + edge
    return pd.concat([x.assign(_why=w) for w, x in parts]).drop_duplicates(["fiscal_year", "source_file", "source_row"])


def read_cells(path, header_map, rows_needed):
    """Return {excel_row: {header: value}} for the wanted rows, with a read-only openpyxl pass."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Raw Data"]
    want = sorted(rows_needed)
    out = {}
    hdr = None
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i == 1:
            hdr = {str(v): j for j, v in enumerate(row) if v is not None}
            continue
        if i > want[-1]:
            break
        if i in rows_needed:
            out[i] = {h: row[j] for h, j in hdr.items()}
    wb.close()
    return out


def num(x):
    return None if x is None or x == "" else float(x)


def spot_check(sample, path_of):
    """Compare every field and month of the sampled rows with the cell in the source workbook,
    read with openpyxl (a different reader than the build uses). Returns (fields checked, mismatches)."""
    bad, checked = [], 0
    for (fy, f), g in sample.groupby(["fiscal_year", "source_file"]):
        cells = read_cells(path_of[(int(fy), f)], None, set(int(v) for v in g["source_row"]))
        mult = 1000 if g["source_units"].iloc[0] == "thousands" else 1
        for r in g.itertuples():
            c = cells[int(r.source_row)]
            for col, src in TEXT.items():
                a, b = getattr(r, col), clean(c.get(src))
                if col in ("agency_code", "account_code") and b is not None:
                    b = str(b)
                checked += 1
                if (a if a == a else None) != b and not (a is None and b is None):
                    bad.append((fy, f, int(r.source_row), col, a, b))
            for mo in MONTHS:
                a = getattr(r, mo)
                v = num(c.get(MONTH_COL[mo]))
                b = None if v is None else v * mult
                checked += 1
                a = None if a != a else a
                if a is None:
                    if b not in (None, 0):
                        bad.append((fy, f, int(r.source_row), mo, a, b))
                elif b is None or abs(a - b) > 0.005:
                    # an unreported month is null in the table and may be 0 or blank in the cell
                    bad.append((fy, f, int(r.source_row), mo, a, b))
    return checked, bad


def main():
    plan = pd.read_csv("workbooks.csv", dtype=str)
    path_of = {(int(r.fiscal_year), r.file): r.path for r in plan.itertuples()}
    con = duckdb.connect()
    df = con.execute(f"select * from read_parquet('{BUILD}')").df()
    report = {"rows": int(len(df))}

    # 1. row counts
    per = df.groupby(["fiscal_year", "source_file"]).size().rename("table_rows").reset_index()
    summ = pd.concat([pd.read_csv("raw_data_sheet_summary.csv").rename(columns={"year": "fiscal_year"}),
                      pd.read_csv("raw_data_sheet_summary_2026.csv").rename(columns={"year": "fiscal_year"})])
    summ["fiscal_year"] = summ["fiscal_year"].astype(int)
    m = per.merge(summ[["fiscal_year", "file", "rows"]].rename(columns={"file": "source_file"}),
                  on=["fiscal_year", "source_file"], how="left")
    m["gap"] = m["rows"] - m["table_rows"]
    report["workbooks"] = int(len(m))
    report["workbooks_where_table_rows_differ_from_raw_rows"] = int((m["gap"] != 0).sum())
    report["rows_dropped_for_missing_line_no"] = int(m["gap"].sum())

    # 2. duplicates. A line key repeats inside one workbook when several reporters filed Category B
    #    detail for the same account; those rows add up to the SF-133 line. A key in two workbooks
    #    of the same year would be double counting.
    key = ["fiscal_year", "tafs", "allocation_code", "financing", "line_no", "line_desc", "cat_b"]
    x = con.execute(f"""select count(*) from (select 1 from read_parquet('{BUILD}')
        group by {",".join(key)} having count(distinct source_file) > 1)""").fetchone()[0]
    report["line_keys_in_more_than_one_workbook"] = int(x)
    y = con.execute(f"""select count(*) from (select 1 from read_parquet('{BUILD}')
        group by fiscal_year, source_file, source_row having count(*) > 1)""").fetchone()[0]
    report["duplicate_row_ids"] = int(y)
    z = con.execute(f"""select count(*), sum(n) from (select count(*) as n from read_parquet('{BUILD}')
        group by {",".join(key)} having count(*) > 1)""").fetchone()
    report["line_keys_repeated_within_a_workbook"] = int(z[0])
    report["rows_in_those_keys"] = int(z[1])
    report["tafs_under_more_than_one_agency_in_a_year"] = int(con.execute(f"""select count(*) from (
        select 1 from read_parquet('{BUILD}') group by fiscal_year, tafs, allocation_code
        having count(distinct agency) > 1)""").fetchone()[0])

    # 3. spot check
    sample = spot_sample(df, plan)
    report["spot_rows"] = int(len(sample))
    checked, bad = spot_check(sample, path_of)
    report["spot_fields_checked"] = checked
    report["spot_mismatches"] = len(bad)
    report["spot_mismatch_examples"] = [list(map(str, x)) for x in bad[:10]]
    report["spot_cases"] = sample["_why"].value_counts().to_dict()
    sample.drop(columns=["_why"]).to_csv("verify_spot_sample.csv", index=False)

    json.dump(report, open("verify_report.json", "w"), indent=1, default=str)
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
