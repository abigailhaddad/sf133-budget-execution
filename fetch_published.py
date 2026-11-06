#!/usr/bin/env python3
"""Download the published tables (and the saved source state) from Hugging Face into ./pub.

    python3 fetch_published.py [--out pub]

Also writes pub/revision.txt, the commit the files came from. publish_to_hf.py hands that to Hugging Face
as the parent commit, so if someone else published in the meantime the upload is refused, not merged blind.
The dataset is public; HF_TOKEN is used if set but not needed.
Exit 4 if the dataset does not exist yet (do the first build by hand, see HANDOFF.md).
"""
import argparse
import os
import shutil
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError

REPO_ID = os.environ.get("SF133_HF_REPO", "abigailhaddad/sf133-budget-execution")
FILES = {"data/sf133_lines.parquet": "sf133_lines.parquet",
         "data/sf133_accounts.parquet": "sf133_accounts.parquet",
         "data/sf133_workbooks.parquet": "sf133_workbooks.parquet"}
STATE = ("state/source_state.json", "source_state.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pub")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("HF_TOKEN") or None
    api = HfApi(token=token)
    try:
        sha = api.dataset_info(REPO_ID).sha
    except RepositoryNotFoundError:
        raise SystemExit(f"{REPO_ID} does not exist yet. Build and publish it by hand first (HANDOFF.md).") from None
    for remote, local in FILES.items():
        p = hf_hub_download(REPO_ID, remote, repo_type="dataset", revision=sha, token=token)
        shutil.copyfile(p, out / local)
        print(f"{local}: {(out / local).stat().st_size / 1e6:.1f} MB")
    try:
        p = hf_hub_download(REPO_ID, STATE[0], repo_type="dataset", revision=sha, token=token)
        shutil.copyfile(p, out / STATE[1])
        print("source_state.json: found")
    except EntryNotFoundError:
        print("source_state.json: none yet (first run)")
    (out / "revision.txt").write_text(sha)
    print("revision", sha)


if __name__ == "__main__":
    main()
