"""Rebuild only what changed, and merge it into the published tables.

The published lines table is read as it is. Rows of the workbooks that changed are dropped, the
re-read workbooks are added, and everything is written back in the original order
(fiscal year, workbook name, Excel row). Other years are never re-read from source.
"""
import json
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import build_sf133
from refresh_lib import MONTH_ORDER

WORKBOOK_COLS = ["fiscal_year", "source_file", "rows_in_table", "units", "agencies", "months_with_data"]


def parse_changed(raw_dir, changed, out_dir, schema_from):
    """Parse each changed workbook to its own parquet file with the published table's column types.

    changed       [{"fiscal_year", "name"}]
    raw_dir       the downloaded workbooks, at <raw_dir>/<fiscal_year>/<name>
    Returns (list of parquet paths, list of workbook report dicts, row counts per (fy, name)).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    schema = pq.read_schema(schema_from)
    parts, reports, counts = [], [], {}
    for c in changed:
        fy, name = int(c["fiscal_year"]), c["name"]
        df, rep = build_sf133.parse_workbook(Path(raw_dir) / str(fy) / name, fy)
        tbl = pa.Table.from_pandas(df, preserve_index=False)
        missing = [n for n in schema.names if n not in tbl.column_names]
        if missing:
            raise ValueError(f"{name}: the parser no longer produces {missing}")
        tbl = tbl.select(schema.names).cast(schema)
        path = out_dir / f"{fy}_{name}.parquet"
        pq.write_table(tbl, path, compression="zstd")
        parts.append(str(path))
        reports.append({"fiscal_year": fy, **rep})
        counts[(fy, name)] = len(df)
    return parts, reports, counts


def _q(s):
    return str(s).replace("'", "''")


def merge_lines(published, parts, replaced, out):
    """Published rows minus the replaced workbooks, plus the new parts, in the published order.

    replaced   [(fiscal_year, source_file)] to drop from the published rows
    """
    con = duckdb.connect()
    pairs = ",".join(f"({int(fy)}, '{_q(name)}')" for fy, name in replaced)
    where = f"where (fiscal_year, source_file) not in ({pairs})" if pairs else ""
    q = f"select * from read_parquet('{_q(published)}') {where}"
    for p in parts:
        q += f" union all by name select * from read_parquet('{_q(p)}')"
    con.execute(f"copy ({q} order by fiscal_year, source_file, source_row) "
                f"to '{_q(out)}' (format parquet, compression zstd)")


def merge_workbooks(published_df, reports, replaced):
    """The one-row-per-workbook table, with the replaced workbooks swapped for the new reports."""
    drop = {(int(fy), name) for fy, name in replaced}
    mask = pd.Series([(int(r.fiscal_year), r.source_file) not in drop for r in published_df.itertuples()],
                     index=published_df.index, dtype=bool)
    keep = published_df[mask]
    new = pd.DataFrame([{
        "fiscal_year": r["fiscal_year"], "source_file": r["file"], "rows_in_table": r["rows"],
        "units": r["units"], "agencies": r["agencies"], "months_with_data": ",".join(r["months_with_data"]),
    } for r in reports], columns=WORKBOOK_COLS)
    out = pd.concat([keep[WORKBOOK_COLS], new], ignore_index=True)
    out = out.astype(published_df[WORKBOOK_COLS].dtypes.to_dict())
    return out.sort_values(["fiscal_year", "source_file"]).reset_index(drop=True)


_MONTH_SUM = " + ".join(f"round(coalesce({m}, 0) * 100)::hugeint" for m in MONTH_ORDER)


def line_fingerprints(lines_path):
    """Per fiscal year: row count and exact integer sums of every month (in cents) and of source_row.
    Two tables with the same fingerprint for a year hold the same numbers for that year."""
    con = duckdb.connect()
    rows = con.execute(f"""select fiscal_year, count(*), sum({_MONTH_SUM}), sum(source_row)
                           from read_parquet('{_q(lines_path)}') group by 1 order by 1""").fetchall()
    return {int(r[0]): (int(r[1]), int(r[2]), int(r[3])) for r in rows}


def account_fingerprints(accounts_path):
    con = duckdb.connect()
    rows = con.execute(f"""select fiscal_year, count(*), sum(round(coalesce(total_budgetary_resources, 0) * 100)::hugeint)
                           from read_parquet('{_q(accounts_path)}') group by 1 order by 1""").fetchall()
    return {int(r[0]): (int(r[1]), int(r[2])) for r in rows}


def summarize(lines_path, accounts_path):
    """What the guard compares: counts and fingerprints per fiscal year."""
    lf = line_fingerprints(lines_path)
    af = account_fingerprints(accounts_path)
    return {"lines": {fy: v[0] for fy, v in lf.items()}, "fingerprints": lf, "accounts": af}


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, default=str))
