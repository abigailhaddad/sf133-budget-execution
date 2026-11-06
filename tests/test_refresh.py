"""Tests for the automatic refresh. No network: pages, downloads and robots.txt are all faked."""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_sf133 as b
import check_updates as cu
import download_changed as dl
import make_card as mc
import make_tables as mt
import maxgov
import refresh_data as rd
import refresh_lib as lib
from test_build import make_workbook, row

PAGE = """
<html><body>
<p>FY 2026 - SF 133 Reports on Budget Execution and Budgetary Resources last updated on 2026-10-21</p>
<table>
<tr><td><a href="attachments/111/FY2026_SF133_MONTHLY_Legislative_Branch.xlsx"
   data-linked-resource-id="9001" data-linked-resource-version="10">Legislative Branch</a></td></tr>
<tr><td><a href="attachments/111/FY2026_SF133_MONTHLY_Judicial_Branch.xlsx"
   data-linked-resource-id="9002" data-linked-resource-version="12">Judicial Branch</a></td></tr>
<tr><td><a href="attachments/111/FY2026_SF133_MONTHLY_Judicial_Branch.pdf">pdf</a></td></tr>
<tr><td><a href="attachments/111/Ab_Sign_Rpt_2026_02.xls">other</a></td></tr>
<tr><td><a href="attachments/110/FY2025_SF133_MONTHLY_Legislative_Branch.xlsx"
   data-linked-resource-id="8001" data-linked-resource-version="3">last year's file</a></td></tr>
</table></body></html>
"""


# ---- reading OMB's page ------------------------------------------------------------------------

def test_page_gives_the_update_date_and_only_this_years_monthly_workbooks():
    p = lib.parse_fy_page(PAGE, 2026, url="https://portal.max.gov/portal/document/SF133/Budget/FY.html")
    assert p["last_updated"] == "2026-10-21"
    assert set(p["files"]) == {"FY2026_SF133_MONTHLY_Legislative_Branch.xlsx", "FY2026_SF133_MONTHLY_Judicial_Branch.xlsx"}
    f = p["files"]["FY2026_SF133_MONTHLY_Judicial_Branch.xlsx"]
    assert f["version"] == 12 and f["resource_id"] == "9002"
    assert f["href"] == "https://portal.max.gov/portal/document/SF133/Budget/attachments/111/FY2026_SF133_MONTHLY_Judicial_Branch.xlsx"


def test_page_with_nothing_on_it_parses_to_nothing():
    p = lib.parse_fy_page("<html><body>maintenance</body></html>", 2026)
    assert p["last_updated"] is None and p["files"] == {}


def test_fiscal_year_turns_over_in_october():
    assert lib.current_fiscal_year(dt.date(2026, 9, 30)) == 2026
    assert lib.current_fiscal_year(dt.date(2026, 10, 1)) == 2027
    assert lib.years_to_check(dt.date(2026, 11, 6)) == [2028, 2027, 2026]


# ---- deciding what changed ---------------------------------------------------------------------

def _page(versions, updated="2026-10-21", fy=2026):
    return {"fiscal_year": fy, "last_updated": updated,
            "files": {n: {"href": f"https://x/{n}", "version": v, "resource_id": n} for n, v in versions.items()}}


def test_a_bumped_version_is_a_change_and_an_unchanged_one_is_not():
    page = _page({"a.xlsx": 11, "b.xlsx": 12})
    state = {"files": {"a.xlsx": {"version": 10}, "b.xlsx": {"version": 12}}}
    changed, _ = lib.plan_changes(page, state, {"a.xlsx", "b.xlsx"}, "2026-10-21")
    assert [c["name"] for c in changed] == ["a.xlsx"]
    assert "10 -> 11" in changed[0]["reason"]


def test_a_workbook_we_do_not_have_is_new():
    changed, _ = lib.plan_changes(_page({"a.xlsx": 1, "b.xlsx": 1}), {"files": {}}, {"a.xlsx"}, "2026-10-21")
    assert [(c["name"], c["reason"]) for c in changed] == [("b.xlsx", "new workbook")]


def test_first_run_trusts_the_data_when_the_page_is_not_newer():
    changed, _ = lib.plan_changes(_page({"a.xlsx": 1}, "2026-10-21"), None, {"a.xlsx"}, "2026-10-22")
    assert changed == []


def test_first_run_redownloads_when_the_page_is_newer_than_the_data():
    changed, _ = lib.plan_changes(_page({"a.xlsx": 1, "b.xlsx": 1}, "2025-12-11", 2025), None,
                                  {"a.xlsx", "b.xlsx"}, "2025-12-03")
    assert {c["name"] for c in changed} == {"a.xlsx", "b.xlsx"}


def test_a_published_workbook_missing_from_the_page_is_a_warning_not_a_change():
    changed, warnings = lib.plan_changes(_page({"a.xlsx": 1}), {"files": {"a.xlsx": {"version": 1}}},
                                         {"a.xlsx", "gone.xlsx"}, "2026-10-21")
    assert changed == [] and "gone.xlsx" in warnings[0]


def test_next_state_records_every_file_the_page_listed():
    st = lib.next_state({"years": {"2025": {"files": {"old": {}}}}}, {2026: _page({"a.xlsx": 5})}, "now")
    assert st["years"]["2026"]["files"]["a.xlsx"]["version"] == 5
    assert "2025" in st["years"], "years not checked this time are kept"


def _published_names(fy):
    return {f"FY{fy}_SF133_MONTHLY_A.xlsx"}


def test_check_reports_404_layout_changes_and_changes():
    cur = 2026
    html = {2026: PAGE.replace("Legislative_Branch", "A").replace("Judicial_Branch", "B")}

    def fetch(fy):
        if fy == 2027:
            return 404, ""
        if fy == 2025:
            return 200, "<html>login required</html>"
        return 200, html[fy]

    res = cu.check([2027, 2026, 2025], {2026: {"FY2026_SF133_MONTHLY_A.xlsx"}}, {2026: "2026-10-21"},
                   {"years": {"2026": {"files": {"FY2026_SF133_MONTHLY_A.xlsx": {"version": 9}}}}}, fetch,
                   today=dt.date(2026, 11, 6))
    assert any("FY2027" in w for w in res["warnings"])
    assert any("FY2025" in p and "layout" in p for p in res["problems"])
    names = {c["name"] for c in res["changed"]}
    assert names == {"FY2026_SF133_MONTHLY_A.xlsx", "FY2026_SF133_MONTHLY_B.xlsx"}


def test_years_whose_workbooks_use_other_names_are_reported_not_refreshed():
    page_html = PAGE.replace("2026-10-21", "2026-12-01")
    res = cu.check([2026], {2026: {"1405160423.xlsx"}}, {2026: "2026-10-21"}, None, lambda fy: (200, page_html))
    assert res["changed"] == []
    assert any("by hand" in w for w in res["warnings"])


# ---- robots.txt and blocks ---------------------------------------------------------------------

def test_robots_that_disallow_everything_stop_the_run(monkeypatch):
    monkeypatch.delenv("SF133_OVERRIDE_ROBOTS", raising=False)
    fetch = lambda url: "User-agent: *\nDisallow: /\n"
    assert maxgov.robots_allows("https://portal.max.gov/portal/document/x.html", fetch) is False
    with pytest.raises(maxgov.RobotsDisallow):
        maxgov.require_permission("https://portal.max.gov/portal/document/x.html", fetch)


def test_robots_that_allow_the_path_let_the_run_go(monkeypatch):
    monkeypatch.delenv("SF133_OVERRIDE_ROBOTS", raising=False)
    fetch = lambda url: "User-agent: *\nAllow: /\n"
    maxgov.require_permission("https://portal.max.gov/portal/document/x.html", fetch)


def test_the_owner_can_override_and_it_does_not_even_read_robots(monkeypatch):
    monkeypatch.setenv("SF133_OVERRIDE_ROBOTS", "yes")
    def boom(url):
        raise AssertionError("robots.txt should not be requested")
    maxgov.require_permission("https://portal.max.gov/x", boom)


def test_the_user_agent_says_who_is_asking():
    assert "sf133-dataset" in maxgov.UA and "github.com/abigailhaddad" in maxgov.UA
    assert "Mozilla" not in maxgov.UA


# ---- downloading -------------------------------------------------------------------------------

def _xlsx_bytes(tmp_path, sheets=True):
    f = tmp_path / "w.xlsx"
    make_workbook(f, [row("A", "B", "11-0100 /X", 2500, 1, 2)])
    if not sheets:
        import openpyxl
        wb = openpyxl.Workbook()
        wb.save(f)
    data = f.read_bytes()
    return data + b"\0" * max(0, dl.MIN_BYTES - len(data))


def test_download_saves_a_workbook(tmp_path):
    data = _xlsx_bytes(tmp_path)
    c = {"fiscal_year": 2026, "name": "FY2026_SF133_MONTHLY_A.xlsx", "href": "https://x/a.xlsx"}
    p = dl.download_one(c, tmp_path / "raw", get=lambda url, timeout=0: (200, {}, data), sleep=lambda s: None)
    assert p == tmp_path / "raw" / "2026" / c["name"] and p.exists()


def test_a_web_page_where_a_workbook_should_be_stops_the_run(tmp_path):
    c = {"fiscal_year": 2026, "name": "FY2026_SF133_MONTHLY_A.xlsx", "href": "https://x/a.xlsx"}
    with pytest.raises(maxgov.Blocked):
        dl.download_one(c, tmp_path, get=lambda url, timeout=0: (200, {}, b"<html>" + b" " * 6000), sleep=lambda s: None)


def test_a_403_is_not_retried(tmp_path):
    calls = []
    def get(url, timeout=0):
        calls.append(url)
        raise maxgov.Blocked("403")
    c = {"fiscal_year": 2026, "name": "FY2026_SF133_MONTHLY_A.xlsx", "href": "https://x/a.xlsx"}
    with pytest.raises(maxgov.Blocked):
        dl.download_one(c, tmp_path, get=get, sleep=lambda s: None)
    assert len(calls) == 1


def test_network_trouble_is_retried_with_a_pause_then_gives_up(tmp_path):
    waits, calls = [], []
    def get(url, timeout=0):
        calls.append(1)
        raise OSError("connection reset")
    c = {"fiscal_year": 2026, "name": "FY2026_SF133_MONTHLY_A.xlsx", "href": "https://x/a.xlsx"}
    with pytest.raises(RuntimeError):
        dl.download_one(c, tmp_path, get=get, sleep=waits.append)
    assert len(calls) == 3 and waits == [5, 20]


def test_a_workbook_without_the_expected_sheets_is_refused(tmp_path):
    data = _xlsx_bytes(tmp_path, sheets=False)
    c = {"fiscal_year": 2026, "name": "FY2026_SF133_MONTHLY_A.xlsx", "href": "https://x/a.xlsx"}
    with pytest.raises(RuntimeError, match="Raw Data"):
        dl.download_one(c, tmp_path, get=lambda url, timeout=0: (200, {}, data), sleep=lambda s: None)
    assert not (tmp_path / "2026" / c["name"]).exists()


# ---- rebuilding only what changed --------------------------------------------------------------

def _build_published(tmp_path):
    """A published dataset with two years and two workbooks each, built the way the real one was."""
    raw = tmp_path / "raw"
    frames, reports = [], []
    for fy in (2025, 2026):
        (raw / str(fy)).mkdir(parents=True)
        for i, ag in enumerate(("Alpha", "Beta")):
            name = f"FY{fy}_SF133_MONTHLY_{ag}.xlsx"
            make_workbook(raw / str(fy) / name, [
                row(ag, "Bur", f"11-0{i}00 /X - Acct {ag}", 2500, 10 + i, 20 + i),
                row(ag, "Bur", f"11-0{i}00 /X - Acct {ag}", 2490, 1, 2),
            ])
            df, rep = b.parse_workbook(raw / str(fy) / name, fy)
            df["source_updated"] = f"{fy}-12-03"
            frames.append(df)
            reports.append({"fiscal_year": fy, **rep})
    pub = tmp_path / "pub"
    pub.mkdir()
    lines = pd.concat(frames, ignore_index=True).sort_values(["fiscal_year", "source_file", "source_row"])
    for c in lines.select_dtypes("object").columns:      # the real table's text columns are strings, even when empty
        lines[c] = lines[c].astype("string")
    lines.to_parquet(pub / "sf133_lines.parquet", index=False)
    acc, _ = mt.build_accounts(pub / "sf133_lines.parquet")
    acc.to_parquet(pub / "sf133_accounts.parquet", index=False)
    wb = rd.merge_workbooks(pd.DataFrame(columns=rd.WORKBOOK_COLS).astype(
        {"fiscal_year": "int64", "source_file": "object", "rows_in_table": "int64", "units": "object",
         "agencies": "int64", "months_with_data": "object"}), reports, [])
    wb.to_parquet(pub / "sf133_workbooks.parquet", index=False)
    return pub, raw


def test_only_the_changed_workbook_is_replaced_and_everything_else_is_untouched(tmp_path):
    pub, raw = _build_published(tmp_path)
    name = "FY2026_SF133_MONTHLY_Alpha.xlsx"
    # OMB posts a revised workbook: same rows, one new amount, and a third row.
    make_workbook(raw / "2026" / name, [
        row("Alpha", "Bur", "11-0000 /X - Acct Alpha", 2500, 99, 98),
        row("Alpha", "Bur", "11-0000 /X - Acct Alpha", 2490, 1, 2),
        row("Alpha", "Bur", "11-0900 /X - Acct New", 2500, 5, 5),
    ])
    changed = [{"fiscal_year": 2026, "name": name}]
    before = rd.summarize(pub / "sf133_lines.parquet", pub / "sf133_accounts.parquet")

    out = tmp_path / "build"
    parts, reports, counts = rd.parse_changed(raw, changed, out / "parts", pub / "sf133_lines.parquet")
    rd.merge_lines(pub / "sf133_lines.parquet", parts, [(2026, name)], out / "sf133_lines.parquet")
    wb = rd.merge_workbooks(pd.read_parquet(pub / "sf133_workbooks.parquet"), reports, [(2026, name)])
    acc, _ = mt.build_accounts(out / "sf133_lines.parquet")
    acc.to_parquet(out / "sf133_accounts.parquet", index=False)
    after = rd.summarize(out / "sf133_lines.parquet", out / "sf133_accounts.parquet")

    assert after["fingerprints"][2025] == before["fingerprints"][2025]          # FY2025 untouched
    assert after["accounts"][2025] == before["accounts"][2025]
    assert after["lines"][2026] == before["lines"][2026] + 1                    # one row added in FY2026
    merged = pd.read_parquet(out / "sf133_lines.parquet")
    assert merged.loc[(merged.source_file == name) & (merged.line_no == 2500) & (merged.tafs.str.contains("Alpha")), "nov"].iloc[0] == 99
    assert merged.loc[merged.source_file == "FY2026_SF133_MONTHLY_Beta.xlsx", "nov"].tolist() == [11, 1]  # Beta kept as published
    key = merged[["fiscal_year", "source_file", "source_row"]]
    assert key.equals(key.sort_values(["fiscal_year", "source_file", "source_row"]).reset_index(drop=True)), "original order"
    assert wb.loc[wb.source_file == name, "rows_in_table"].iloc[0] == 3
    assert len(wb) == 4
    assert lib.guard(before, after, {2026}) == []


def test_merging_nothing_gives_back_the_published_table_exactly(tmp_path):
    pub, _ = _build_published(tmp_path)
    out = tmp_path / "same.parquet"
    rd.merge_lines(pub / "sf133_lines.parquet", [], [], out)
    assert rd.line_fingerprints(out) == rd.line_fingerprints(pub / "sf133_lines.parquet")
    a, b2 = pd.read_parquet(out), pd.read_parquet(pub / "sf133_lines.parquet")
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b2.reset_index(drop=True), check_dtype=False)


def test_a_new_workbook_is_added_in_order(tmp_path):
    pub, raw = _build_published(tmp_path)
    name = "FY2026_SF133_MONTHLY_Aardvark.xlsx"                                  # sorts first in FY2026
    make_workbook(raw / "2026" / name, [row("Aardvark", "Bur", "22-0100 /X - Acct Aard", 2500, 1, 2)])
    parts, reports, _ = rd.parse_changed(raw, [{"fiscal_year": 2026, "name": name}], tmp_path / "parts",
                                         pub / "sf133_lines.parquet")
    out = tmp_path / "m.parquet"
    rd.merge_lines(pub / "sf133_lines.parquet", parts, [(2026, name)], out)
    m = pd.read_parquet(out)
    assert m[m.fiscal_year == 2026].source_file.iloc[0] == name
    wb = rd.merge_workbooks(pd.read_parquet(pub / "sf133_workbooks.parquet"), reports, [(2026, name)])
    assert len(wb) == 5


# ---- the guard ---------------------------------------------------------------------------------

def _summary(lines, accounts=None, fp=None):
    return {"lines": lines, "accounts": accounts or {fy: (n // 2, n) for fy, n in lines.items()},
            "fingerprints": fp or {fy: (n, n * 7, n * 3) for fy, n in lines.items()}}


def test_guard_passes_when_untouched_years_are_identical_and_the_changed_year_grows():
    old = _summary({2025: 1000, 2026: 1000})
    new = _summary({2025: 1000, 2026: 1010})
    new["fingerprints"][2025] = old["fingerprints"][2025]
    new["accounts"][2025] = old["accounts"][2025]
    assert lib.guard(old, new, {2026}) == []


def test_guard_refuses_when_an_untouched_year_moves():
    old = _summary({2025: 1000, 2026: 1000})
    new = _summary({2025: 999, 2026: 1000})
    problems = lib.guard(old, new, {2026})
    assert any("FY2025 was not touched" in p for p in problems)


def test_guard_refuses_when_untouched_values_change_with_the_same_row_count():
    old = _summary({2025: 1000})
    new = _summary({2025: 1000}, fp={2025: (1000, 1, 3000)})
    assert any("values changed" in p for p in lib.guard(old, new, set()))


def test_guard_refuses_a_changed_year_that_loses_more_than_two_percent():
    old = _summary({2026: 1000})
    assert lib.guard(old, _summary({2026: 985}), {2026}) == []
    assert any("shrank" in p for p in lib.guard(old, _summary({2026: 970}), {2026}))


def test_guard_refuses_a_missing_year():
    old = _summary({2025: 1000, 2026: 1000})
    assert any("missing" in p for p in lib.guard(old, _summary({2026: 1000}), {2026}))


# ---- the card ----------------------------------------------------------------------------------

def test_the_card_is_filled_from_the_tables(tmp_path):
    pub, _ = _build_published(tmp_path)
    tpl = ROOT / "dataset_card" / "README.template.md"
    v = mc.compute(pub)
    card = mc.render(tpl.read_text(), v)
    assert "{{" not in card
    assert "FY2025 to FY2026" in card
    assert "| 2026 | 2026-12-03 | 4 |" in card                 # as-of table row: 2 workbooks x 2 lines
    assert "FY2025 runs through December, FY2026 runs through December." in card


def test_a_template_placeholder_with_no_value_is_an_error():
    with pytest.raises(KeyError):
        mc.render("hello {{nothing_fills_this}}", {})


def test_short_tafs_drops_the_period_code():
    assert mc.short_tafs("97-0040 /X - Payment to Military Retirement Fund") == "97-0040 Payment to Military Retirement Fund"


def test_state_only_upload_is_skipped_when_nothing_changed(tmp_path, monkeypatch, capsys):
    import publish_to_hf as ph
    pub = tmp_path / "pub"
    pub.mkdir()
    st = {"schema": 1, "checked_at": "t1", "years": {"2026": {"files": {"a": {"version": 1}}}}}
    (pub / "source_state.json").write_text(json.dumps(st))
    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"state_next": {**st, "checked_at": "t2"}}))
    monkeypatch.setattr(ph, "PUB", pub)
    ph.publish_state_only(str(changes), upload=False)
    assert "nothing to upload" in capsys.readouterr().out
