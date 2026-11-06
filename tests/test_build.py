"""Tests for the SF-133 build. They use a tiny synthetic workbook, so they need no downloads."""
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_sf133 as b

HEADER = ["RPT_YR", "AGENCY", "BUREAU", "OMB_ACCT", "TRAG", "ALLOC", "TRACCT", "FY1", "FY2", "STAT",
          "CRED_IND", "LINENO", "LINE_DESC", "CAT_B", "TAFS", "TAFS_ACCT", "OMB_ACCOUNT", "SECTION",
          "SECTION_NO", "LINE_TYPE", "LAST_UPDATED", "AMT_NOV", "AMT1", "AMT_JAN", "AMT2"]


def make_workbook(path, rows, units="(Dollars)"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TAFS detail"
    ws["A1"] = "OFFICE OF MANAGEMENT AND BUDGET"
    ws["A4"] = units
    raw = wb.create_sheet("Raw Data")
    raw.append(HEADER)
    for r in rows:
        raw.append(r)
    wb.save(path)


def row(agency, bureau, tafs, line, nov, dec, jan=0, mar=0, acct="0100", trag="95"):
    return [2025, agency, bureau, "999-00-0100  X", trag, None, acct, None, "X", "X",
            "NON-FINANCING ACCOUNTS", line, "Total budgetary resources", None, tafs, "Acct",
            "Acct", "STATUS OF BUDGETARY RESOURCES", 2, "S", "2025-12-03", nov, dec, jan, mar]


def test_each_row_keeps_its_own_agency(tmp_path):
    """The old pipeline named every row after the first agency in the workbook."""
    f = tmp_path / "wb.xlsx"
    make_workbook(f, [
        row("400 Years of African-American History Commission", "400 Years", "48-5721 /20", 2500, 5, 5),
        row("Federal Deposit Insurance Corporation", "Deposit Insurance", "51-4596 /X", 2500, 100, 130),
    ])
    df, rep = b.parse_workbook(f, 2025)
    got = dict(zip(df["tafs"], df["agency"]))
    assert got["51-4596 /X"] == "Federal Deposit Insurance Corporation"
    assert got["48-5721 /20"] == "400 Years of African-American History Commission"
    assert rep["agencies"] == 2


def test_thousands_are_scaled_to_dollars(tmp_path):
    f = tmp_path / "wb.xlsx"
    make_workbook(f, [row("A", "B", "11-0100 /X", 2500, 2, 3)], units="(Thousands)")
    df, _ = b.parse_workbook(f, 2016)
    assert df["nov"].iloc[0] == 2000 and df["dec"].iloc[0] == 3000


def test_unreported_month_is_null_not_zero(tmp_path):
    f = tmp_path / "wb.xlsx"
    make_workbook(f, [row("A", "B", "11-0100 /X", 2500, 2, 3)])
    df, rep = b.parse_workbook(f, 2025)
    assert df["feb"].isna().all() and df["oct"].isna().all()
    assert df["nov"].notna().all()
    assert rep["months_with_data"] == ["Nov", "Dec"]


def test_quarter_end_months_come_from_amt1_to_amt4(tmp_path):
    f = tmp_path / "wb.xlsx"
    make_workbook(f, [row("A", "B", "11-0100 /X", 2500, 1, 2, jan=3, mar=4)])
    df, _ = b.parse_workbook(f, 2025)
    r = df.iloc[0]
    assert (r["nov"], r["dec"], r["jan"], r["mar"]) == (1, 2, 3, 4)


def test_ids_stay_text_and_source_row_points_at_excel_row(tmp_path):
    f = tmp_path / "wb.xlsx"
    make_workbook(f, [row("A", "B", "11-0100 /X", 2500, 1, 2, acct="0100", trag="05"),
                      row("A", "B", "11-0200 /X", 2500, 1, 2, acct="0200", trag="05")])
    df, _ = b.parse_workbook(f, 2025)
    assert df["agency_code"].tolist() == ["05", "05"]
    assert df["account_code"].tolist() == ["0100", "0200"]
    assert df["source_row"].tolist() == [2, 3]


def test_text_cleaning_removes_excel_line_break_artifacts():
    assert b.clean("11-0100 /X - Salaries_x000D_\nand Expenses") == "11-0100 /X - Salaries and Expenses"
    assert b.clean(None) is None
