#!/usr/bin/env python3
"""Write the dataset card (README.md on Hugging Face) from the built tables, so every number is computed.

    python3 make_card.py [--build build] [--template dataset_card/README.template.md] [--out build/README.md]

The template holds the wording. Anything in double braces, like {{lines_rows}}, is filled from the tables
in --build (and from refresh_report.json there, when a refresh wrote one). Nothing about the data is typed
into the template by hand except history that does not change (what the first build checked, what was
left out).
"""
import argparse
import json
import re
from pathlib import Path

import duckdb

MONTH_NAMES = {"oct": "October", "nov": "November", "dec": "December", "jan": "January", "feb": "February",
               "mar": "March", "apr": "April", "may": "May", "jun": "June", "jul": "July", "aug": "August",
               "sep": "September"}


def short_tafs(t):
    """'97-0040 /X - Payment to Military Retirement Fund' -> '97-0040 Payment to Military Retirement Fund'."""
    m = re.match(r"^(\S+)\s+/\S+\s+-\s+(.*)$", t or "")
    return f"{m.group(1)} {m.group(2)}" if m else (t or "")


def fy_range(a, b):
    return a if a == b else f"{a} to {b}"


def compute(build, report=None):
    build = Path(build)
    con = duckdb.connect()
    L, A, W = (f"read_parquet('{build / n}')" for n in ("sf133_lines.parquet", "sf133_accounts.parquet", "sf133_workbooks.parquet"))
    v = {}
    n_lines = con.execute(f"select count(*) from {L}").fetchone()[0]
    n_acc = con.execute(f"select count(*) from {A}").fetchone()[0]
    n_wb = con.execute(f"select count(*) from {W}").fetchone()[0]
    first, last = con.execute(f"select min(fiscal_year), max(fiscal_year) from {L}").fetchone()
    v.update(lines_rows=f"{n_lines:,}", accounts_rows=f"{n_acc:,}", workbooks_rows=f"{n_wb:,}",
             fy_first=str(first), fy_last=str(last))

    # As of: one row per fiscal year. ORDER BY, not min()/max(), on text read from Parquet.
    rows = con.execute(f"""select fiscal_year, min(source_updated), max(source_updated), count(*)
                           from {L} group by 1 order by 1""").fetchall()
    t = ["| Fiscal year | OMB data updated | Lines rows |", "|---|---|---|"]
    for fy, lo, hi, n in rows:
        t.append(f"| {fy} | {fy_range(lo, hi)} | {n:,} |")
    v["asof_table"] = "\n".join(t)

    # Latest reported month per fiscal year, from the accounts table.
    latest = dict(con.execute(f"select distinct fiscal_year, as_of_month from {A} order by 1").fetchall())
    partial = [(fy, m) for fy, m in latest.items() if m != "sep"]
    if not partial:
        v["through_sentence"] = "Every year runs through September."
    else:
        bits = ", ".join(f"FY{fy} runs through {MONTH_NAMES[m]}" for fy, m in partial)
        lead = "Every other year runs through September; " if len(partial) < len(latest) else ""
        v["through_sentence"] = f"{lead}{bits}." if lead else f"{bits}."

    # Totals at each year's latest month.
    q = con.execute(f"""select fiscal_year, as_of_month, count(*),
        count(*) filter (where unobligated_balance_end_of_period is null),
        count(*) filter (where unobligated_balance_end_of_period is null and coalesce(total_budgetary_resources, 0) <> 0),
        sum(total_budgetary_resources),
        sum(total_budgetary_resources) filter (where financing = 'NON-FINANCING ACCOUNTS'),
        sum(total_budgetary_resources) filter (where financing = 'FINANCING ACCOUNTS')
        from {A} group by 1, 2 order by 1""").fetchall()
    t = ["| Fiscal year | Through | Accounts | No line 2490 (unobligated balance is null) | Of those, nonzero total budgetary resources | Total budgetary resources, all ($B) | Non-financing ($B) | Financing ($B) |",
         "|---|---|---|---|---|---|---|---|"]
    for fy, m, n, nnull, nnz, tot, nonfin, fin in q:
        b = lambda x: (x or 0) / 1e9      # a year with no financing accounts sums to null, not zero
        t.append(f"| {fy} | {MONTH_NAMES[m][:3]} | {n:,} | {nnull:,} | {nnz:,} | {b(tot):,.1f} | {b(nonfin):,.1f} | {b(fin):,.1f} |")
    v["totals_table"] = "\n".join(t)

    # The example paragraph: the latest fiscal year that runs through September.
    sep_years = [fy for fy, m in latest.items() if m == "sep"]
    ex = max(sep_years) if sep_years else last
    n_null, n_nz = con.execute(f"""select count(*) filter (where unobligated_balance_end_of_period is null),
        count(*) filter (where unobligated_balance_end_of_period is null and coalesce(total_budgetary_resources, 0) <> 0)
        from {A} where fiscal_year = {ex}""").fetchone()
    big = con.execute(f"""select tafs, total_budgetary_resources from {A}
        where fiscal_year = {ex} and unobligated_balance_end_of_period is null and total_budgetary_resources is not null
        order by total_budgetary_resources desc limit 1""").fetchone()
    v["null2490_paragraph"] = (
        f"Some accounts have no line 2490 row in the September report, so the column is null for them, not zero. "
        f"Their other lines are still here, and some carry real money: in FY{ex}, {n_nz:,} of the {n_null:,} accounts "
        f"with a null balance report a nonzero total budgetary resources. The biggest is {short_tafs(big[0])} "
        f"(${big[1] / 1e9:,.1f}B)." if big else "")

    # An account is a Treasury agency code plus account code, whatever its period of availability.
    v["gift_count"] = str(con.execute(
        f"select count(distinct agency_code || '-' || account_code) from {A} where is_gift_account").fetchone()[0])

    if report:
        names = sorted({f"FY{w['fiscal_year']}" for w in report.get("changed_workbooks", [])})
        v["refresh_note"] = (f" Last automatic refresh: checked {report['checked_at'][:10]}, replaced "
                             f"{len(report['changed_workbooks'])} workbook(s) ({', '.join(names)}).")
    else:
        v["refresh_note"] = ""
    return v


def render(template, values):
    missing = set(re.findall(r"\{\{(\w+)\}\}", template)) - set(values)
    if missing:
        raise KeyError(f"the template uses {sorted(missing)} but nothing fills them")
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="build")
    ap.add_argument("--template", default="dataset_card/README.template.md")
    ap.add_argument("--out")
    a = ap.parse_args()
    rp = Path(a.build) / "refresh_report.json"
    report = json.loads(rp.read_text()) if rp.exists() else None
    card = render(Path(a.template).read_text(), compute(a.build, report))
    out = Path(a.out or Path(a.build) / "README.md")
    out.write_text(card)
    print(f"wrote {out} ({len(card):,} chars)")


if __name__ == "__main__":
    main()
