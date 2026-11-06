#!/usr/bin/env python3
"""Build the two small tables that sit beside sf133_lines.parquet.

sf133_accounts.parquet   one row per fiscal year x TAFS x allocation x financing: labels, codes
                         and the headline lines at the latest reported month, by their SF-133 names.
sf133_workbooks.parquet  one row per source workbook: rows, units, months with data, update date.
"""
import json
from pathlib import Path

import duckdb
import pandas as pd

BUILD = Path("build")
LINES = BUILD / "sf133_lines.parquet"

# Headline lines, named as the SF-133 names them (checked against LINE_DESC in the source).
HEADLINE = {
    1000: "unobligated_balance_brought_forward",
    1900: "budget_authority_total",
    1910: "total_budgetary_resources_1910",
    2190: "new_obligations_and_upward_adjustments",
    2490: "unobligated_balance_end_of_period",
    2500: "total_budgetary_resources",
    3020: "outlays_gross_change_in_obligated_balance",
    4190: "outlays_net",
}
GIFT_RULE = r"(?i)\b(gift|gifts|donation|donations|bequest|bequests)\b"


def main():
    con = duckdb.connect()
    con.execute(f"create view l as select * from read_parquet('{LINES}')")

    # Latest month with any reported value per fiscal year (workbook-wide), in fiscal-year order.
    order = ["oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep"]
    latest = {}
    for fy, in con.execute("select distinct fiscal_year from l order by 1").fetchall():
        got = None
        for m in order:
            n = con.execute(f"select count({m}) from l where fiscal_year={fy}").fetchone()[0]
            if n:
                got = m
        latest[fy] = got
    pd.Series(latest).to_json(BUILD / "latest_month.json")

    keys = ["fiscal_year", "agency", "bureau", "tafs", "agency_code", "account_code",
            "allocation_code", "begin_year", "end_year", "availability", "financing"]
    parts = []
    for fy, m in latest.items():
        cases = ",\n          ".join(
            f"sum(case when line_no = {k} then {m} end) as {v}" for k, v in HEADLINE.items())
        q = f"""
        select {", ".join(keys)},
          {cases}
        from l where fiscal_year = {fy}
        group by {", ".join(str(i + 1) for i in range(len(keys)))}"""
        parts.append(con.execute(q).df())
    acc = pd.concat(parts, ignore_index=True)
    acc["as_of_month"] = acc["fiscal_year"].map(latest)
    acc["is_gift_account"] = acc["tafs"].str.contains(GIFT_RULE, regex=True, na=False)
    acc.to_parquet(BUILD / "sf133_accounts.parquet", index=False, compression="zstd")

    rep = json.load(open(BUILD / "build_report.json"))
    wb = pd.DataFrame(rep).rename(columns={"rows": "rows_in_table", "file": "source_file"})
    wb["months_with_data"] = wb["months_with_data"].map(lambda v: ",".join(v))
    wb.to_parquet(BUILD / "sf133_workbooks.parquet", index=False)
    print(len(acc), "accounts rows;", int(acc["is_gift_account"].sum()), "gift-rule rows;", len(wb), "workbooks")


if __name__ == "__main__":
    main()
