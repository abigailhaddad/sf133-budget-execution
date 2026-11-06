#!/usr/bin/env python3
"""Download the workbooks that check_updates.py listed in changes.json. One at a time, with a pause.

    python3 download_changed.py --changes changes.json --raw raw_changed [--max-files 60]

Files land at <raw>/<fiscal_year>/<name>. A file that is already there and passes the checks is kept.
Stops (exit 2) at a 401, 403 or 429, or when a file turns out to be a web page, not a workbook.
Exit 1 after three failed tries on one file (waits 5, then 20 seconds between tries).
Exit 3 if robots.txt disallows automated access and the owner has not overridden it.
"""
import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

import maxgov

XLSX_MAGIC = b"PK\x03\x04"
MIN_BYTES = 5_000


def looks_like_workbook(data):
    """A workbook is a zip file. A login or challenge page is HTML."""
    return data[:4] == XLSX_MAGIC and len(data) >= MIN_BYTES


def has_expected_sheets(path):
    try:
        with zipfile.ZipFile(path) as z:
            wbxml = z.read("xl/workbook.xml").decode("utf-8", "replace")
        return 'name="Raw Data"' in wbxml and 'name="TAFS detail"' in wbxml
    except Exception:
        return False


def download_one(c, raw, get=maxgov.get, sleep=time.sleep, tries=3):
    """Fetch one workbook to <raw>/<fy>/<name>. Returns the path. Raises Blocked or RuntimeError."""
    dest = Path(raw) / str(c["fiscal_year"]) / c["name"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and has_expected_sheets(dest):
        return dest
    last = None
    for attempt in range(tries):
        if attempt:
            sleep(5 * 4 ** (attempt - 1))
        try:
            status, _, body = get(c["href"], timeout=300)
        except maxgov.Blocked:
            raise
        except Exception as e:  # network trouble: try again
            last = f"{type(e).__name__}: {e}"
            continue
        if status == 200 and looks_like_workbook(body):
            part = dest.with_suffix(".part")
            part.write_bytes(body)
            if not has_expected_sheets(part):
                part.unlink()
                raise RuntimeError(f"{c['name']}: downloaded, but it has no 'Raw Data' and 'TAFS detail' sheets. "
                                   "The workbook layout may have changed.")
            part.rename(dest)
            return dest
        if status == 200:
            raise maxgov.Blocked(f"{c['href']} answered 200 with something that is not a workbook "
                                 f"(starts {body[:20]!r}). A login or challenge page?")
        last = f"HTTP {status}"
        if status == 404:
            break
    raise RuntimeError(f"{c['name']}: {last}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--changes", default="changes.json")
    ap.add_argument("--raw", default="raw_changed")
    ap.add_argument("--max-files", type=int, default=60)
    a = ap.parse_args()
    changes = json.loads(Path(a.changes).read_text())["changed"]
    if len(changes) > a.max_files:
        sys.exit(f"{len(changes)} workbooks to download is more than --max-files {a.max_files}. "
                 "Something is off; look at changes.json before raising the limit.")
    if not changes:
        print("nothing to download")
        return
    try:
        maxgov.require_permission(changes[0]["href"])
        for i, c in enumerate(changes):
            if i:
                maxgov.pause()
            p = download_one(c, a.raw)
            print(f"{i + 1}/{len(changes)} FY{c['fiscal_year']} {c['name']} ({p.stat().st_size / 1e6:.1f} MB)", flush=True)
    except maxgov.RobotsDisallow as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        sys.exit(3)
    except maxgov.Blocked as e:
        print(f"STOPPED: {e}. Do not retry from this address today.", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    print("DONE")


if __name__ == "__main__":
    main()
