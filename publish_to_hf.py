#!/usr/bin/env python3
"""Publish the SF-133 dataset to Hugging Face in ONE commit.

    python3 publish_to_hf.py             # dry run: checks the build, writes nothing to Hugging Face
    python3 publish_to_hf.py --upload    # creates the dataset repo if missing, then one commit

The dry run re-reads the build, checks row counts and keys, and prints what would change.
Needs HF_TOKEN (or a cached login) only for --upload and for the dry run's read of the remote.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO_ID = os.environ.get("SF133_HF_REPO", "abigailhaddad/sf133-budget-execution")
BUILD = Path(os.environ.get("SF133_BUILD", "build"))
PUB = Path(os.environ.get("SF133_PUB", "pub"))
FILES = {
    "data/sf133_lines.parquet": BUILD / "sf133_lines.parquet",
    "data/sf133_accounts.parquet": BUILD / "sf133_accounts.parquet",
    "data/sf133_workbooks.parquet": BUILD / "sf133_workbooks.parquet",
    "README.md": BUILD / "README.md",   # written from dataset_card/README.template.md by make_card.py
}
if (BUILD / "source_state.json").exists():
    FILES["state/source_state.json"] = BUILD / "source_state.json"


def make_card():
    """Write build/README.md from the template and the tables, so the card's numbers are computed."""
    import make_card as mc
    rp = BUILD / "refresh_report.json"
    report = json.loads(rp.read_text()) if rp.exists() else None
    card = mc.render(Path("dataset_card/README.template.md").read_text(), mc.compute(BUILD, report))
    (BUILD / "README.md").write_text(card)


def check_build():
    problems = []
    for dest, src in FILES.items():
        if not src.exists():
            problems.append(f"missing {src}")
    if problems:
        return problems, {}
    con = duckdb.connect()
    n_lines = con.execute(f"select count(*) from read_parquet('{FILES['data/sf133_lines.parquet']}')").fetchone()[0]
    n_acc = con.execute(f"select count(*) from read_parquet('{FILES['data/sf133_accounts.parquet']}')").fetchone()[0]
    wb = pd.read_parquet(FILES["data/sf133_workbooks.parquet"])
    if int(wb["rows_in_table"].sum()) != n_lines:
        problems.append(f"workbook manifest says {int(wb['rows_in_table'].sum()):,} rows, lines table has {n_lines:,}")
    dup = con.execute(f"""select count(*) from (select 1 from read_parquet('{FILES['data/sf133_lines.parquet']}')
        group by fiscal_year, tafs, allocation_code, financing, line_no, line_desc, cat_b
        having count(distinct source_file) > 1)""").fetchone()[0]
    if dup:
        problems.append(f"{dup:,} line keys appear in more than one workbook of the same year")
    years = con.execute(f"select fiscal_year, count(*) from read_parquet('{FILES['data/sf133_lines.parquet']}') group by 1 order by 1").fetchall()
    return problems, {"lines": n_lines, "accounts": n_acc, "years": years,
                      "sizes_mb": {k: round(v.stat().st_size / 1e6, 2) for k, v in FILES.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--state-only", metavar="CHANGES_JSON",
                    help="upload only the saved source state from this changes.json, if it differs from the published one")
    a = ap.parse_args()
    if a.state_only:
        return publish_state_only(a.state_only, a.upload)

    make_card()
    problems, info = check_build()
    print(json.dumps(info, indent=1, default=str))
    if problems:
        sys.exit("build check failed:\n  " + "\n  ".join(problems))
    print("build check passed")

    from huggingface_hub import CommitOperationAdd, HfApi
    api = HfApi()
    exists = True
    try:
        api.dataset_info(REPO_ID)
    except Exception:
        exists = False
    print(f"dataset {REPO_ID}: {'exists' if exists else 'does not exist yet'}")
    if not a.upload:
        print("dry run: nothing uploaded (add --upload to commit)")
        return
    if not exists:
        api.create_repo(REPO_ID, repo_type="dataset", exist_ok=True)
    ops = [CommitOperationAdd(path_in_repo=dest, path_or_fileobj=str(src)) for dest, src in FILES.items()]
    fy = [y for y, _ in info["years"]]
    msg = f"SF-133 budget execution, FY{min(fy)} to FY{max(fy)}"
    rp = BUILD / "refresh_report.json"
    if rp.exists():
        r = json.loads(rp.read_text())
        msg = (f"Refresh: replaced {len(r['changed_workbooks'])} workbook(s) in "
               + ", ".join(f"FY{y}" for y in r["years_changed"]))
    # Refuse to overwrite a commit somebody else made after we downloaded the published files.
    parent = (PUB / "revision.txt").read_text().strip() if (PUB / "revision.txt").exists() else None
    api.create_commit(REPO_ID, repo_type="dataset", operations=ops, commit_message=msg, parent_commit=parent)
    print("committed")


def publish_state_only(changes_json, upload):
    """After a check that found nothing to rebuild, remember the versions OMB's page showed.
    Writes only state/source_state.json, and only when its content differs from what is published."""
    from huggingface_hub import CommitOperationAdd, HfApi
    nxt = json.loads(Path(changes_json).read_text())["state_next"]
    cur_p = PUB / "source_state.json"
    cur = json.loads(cur_p.read_text()) if cur_p.exists() else None
    strip = lambda st: (st or {}).get("years")
    if strip(cur) == strip(nxt):
        print("source state unchanged; nothing to upload")
        return
    tmp = BUILD / "source_state.json"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(json.dumps(nxt, indent=1))
    print("source state differs from the published one")
    if not upload:
        print("dry run: nothing uploaded (add --upload to commit)")
        return
    parent = (PUB / "revision.txt").read_text().strip() if (PUB / "revision.txt").exists() else None
    HfApi().create_commit(REPO_ID, repo_type="dataset", commit_message="Refresh check: record source versions",
                          operations=[CommitOperationAdd(path_in_repo="state/source_state.json", path_or_fileobj=str(tmp))],
                          parent_commit=parent)
    print("committed")


if __name__ == "__main__":
    main()
