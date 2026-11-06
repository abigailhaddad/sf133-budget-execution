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
FILES = {
    "data/sf133_lines.parquet": BUILD / "sf133_lines.parquet",
    "data/sf133_accounts.parquet": BUILD / "sf133_accounts.parquet",
    "data/sf133_workbooks.parquet": BUILD / "sf133_workbooks.parquet",
    "README.md": Path("dataset_card/README.md"),
}


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
    a = ap.parse_args()

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
    api.create_commit(REPO_ID, repo_type="dataset", operations=ops,
                      commit_message="SF-133 budget execution, FY2018 to FY2026")
    print("committed")


if __name__ == "__main__":
    main()
