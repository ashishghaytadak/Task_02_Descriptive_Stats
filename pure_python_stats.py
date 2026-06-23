#!/usr/bin/env python3


import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from statistics import mean, median, stdev

# Tokens treated as "missing" everywhere. Keep this identical across all 3 scripts.
NA_TOKENS = {"", "na", "n/a", "nan", "null", "none"}


# --------------------------------------------------------------------------- #
# Type handling
# --------------------------------------------------------------------------- #
def is_missing(value):
    """A cell is missing if it is None or, once stripped/lowercased, a NA token."""
    if value is None:
        return True
    return value.strip().lower() in NA_TOKENS


def parse_number(value):
    """
    Try to interpret a string as a number.

    Returns ('int', int_value), ('float', float_value), or None if not numeric.
    """
    s = value.strip()
    # int() accepts surrounding whitespace and a leading sign but rejects '1.0'
    try:
        return ("int", int(s))
    except ValueError:
        pass
    try:
        f = float(s)
        # Guard against float('nan')/('inf') sneaking through as "numbers".
        if math.isnan(f) or math.isinf(f):
            return None
        return ("float", f)
    except ValueError:
        return None


def infer_column_type(values):
    """
    Decide a column's type from its non-missing values.

    Returns one of 'int', 'float', 'string'. A column with no non-missing values
    is treated as 'string'.
    """
    saw_value = False
    all_int = True
    for v in values:
        if is_missing(v):
            continue
        saw_value = True
        parsed = parse_number(v)
        if parsed is None:
            return "string"  # any non-numeric value forces string
        if parsed[0] == "float":
            all_int = False
    if not saw_value:
        return "string"
    return "int" if all_int else "float"


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def numeric_stats(values):
    """count, mean, min, max, std (sample, ddof=1), median for non-missing values."""
    nums = [parse_number(v)[1] for v in values if not is_missing(v)]
    n = len(nums)
    if n == 0:
        return {"count": 0, "mean": None, "min": None, "max": None,
                "std": None, "median": None}
    return {
        "count": n,
        "mean": mean(nums),
        "min": min(nums),
        "max": max(nums),
        # sample std needs n >= 2; report 0.0 for a single value (matches pandas std of
        # a 1-element series which is NaN -> we use None to be explicit)
        "std": stdev(nums) if n >= 2 else None,
        "median": median(nums),
    }


def categorical_stats(values, top_n=5):
    """count, unique count, mode + frequency, and top-N values by frequency."""
    present = [v.strip() for v in values if not is_missing(v)]
    counter = Counter(present)
    n = len(present)
    if n == 0:
        return {"count": 0, "unique": 0, "mode": None, "mode_freq": 0, "top": []}
    mode_value, mode_freq = counter.most_common(1)[0]
    return {
        "count": n,
        "unique": len(counter),
        "mode": mode_value,
        "mode_freq": mode_freq,
        "top": counter.most_common(top_n),
    }


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_csv(path):
    """Read the whole file into headers + list of row dicts. csv handles quoting."""
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        rows = list(reader)
    return headers, rows


def column_values(rows, col):
    return [row.get(col) for row in rows]


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def analyze(headers, rows, top_n=5):
    """Compute dataset-level stats and per-column stats."""
    report = {
        "row_count": len(rows),
        "column_count": len(headers),
        "columns": {},
        "missing_per_column": {},
        "inferred_types": {},
    }
    for col in headers:
        vals = column_values(rows, col)
        col_type = infer_column_type(vals)
        missing = sum(1 for v in vals if is_missing(v))
        report["inferred_types"][col] = col_type
        report["missing_per_column"][col] = missing
        if col_type in ("int", "float"):
            report["columns"][col] = {"type": col_type, **numeric_stats(vals)}
        else:
            report["columns"][col] = {"type": "string",
                                      **categorical_stats(vals, top_n)}
    return report


def grouped_numeric(headers, rows, group_cols, top_n_groups=10):
    """
    Group rows by group_cols (a list) and compute numeric stats per group.

    Returns a dict with the number of groups and a preview of the largest groups.
    Only numeric columns get aggregated; the grouping keys themselves are skipped.
    """
    # Determine which columns are numeric across the whole dataset (consistent typing).
    numeric_cols = [
        c for c in headers
        if c not in group_cols and infer_column_type(column_values(rows, c)) in ("int", "float")
    ]
    buckets = defaultdict(list)
    for row in rows:
        key = tuple(row.get(c) for c in group_cols)
        buckets[key].append(row)

    summaries = []
    for key, group_rows in buckets.items():
        per_col = {}
        for c in numeric_cols:
            per_col[c] = numeric_stats([r.get(c) for r in group_rows])
        summaries.append({"key": dict(zip(group_cols, key)),
                          "n_rows": len(group_rows),
                          "numeric": per_col})
    summaries.sort(key=lambda s: s["n_rows"], reverse=True)
    return {
        "group_by": group_cols,
        "n_groups": len(buckets),
        "numeric_columns": numeric_cols,
        "preview_largest_groups": summaries[:top_n_groups],
        "all_groups": summaries,  # full data, kept for --out; not printed
    }


# --------------------------------------------------------------------------- #
# Printing
# --------------------------------------------------------------------------- #
def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.4f}"
    return str(x)


def print_report(path, report, group_results):
    print("=" * 78)
    print(f"PURE PYTHON DESCRIPTIVE STATISTICS")
    print(f"Dataset: {path}")
    print("=" * 78)
    print(f"Rows: {report['row_count']:,}    Columns: {report['column_count']}")
    print("\n-- Inferred types & missing values ------------------------------------")
    for col in report["inferred_types"]:
        t = report["inferred_types"][col]
        miss = report["missing_per_column"][col]
        pct = (miss / report["row_count"] * 100) if report["row_count"] else 0
        print(f"  {col:<32} {t:<7} missing={miss:>8,} ({pct:5.1f}%)")

    print("\n-- Per-column statistics ---------------------------------------------")
    for col, stats in report["columns"].items():
        print(f"\n[{col}]  ({stats['type']})")
        if stats["type"] in ("int", "float"):
            print(f"    count={stats['count']:,}  mean={_fmt(stats['mean'])}  "
                  f"std={_fmt(stats['std'])}")
            print(f"    min={_fmt(stats['min'])}  median={_fmt(stats['median'])}  "
                  f"max={_fmt(stats['max'])}")
        else:
            print(f"    count={stats['count']:,}  unique={stats['unique']:,}  "
                  f"mode={stats['mode']!r} (freq={stats['mode_freq']:,})")
            tops = ", ".join(f"{v!r}:{c}" for v, c in stats["top"])
            print(f"    top: {tops}")

    for gr in group_results:
        print("\n" + "=" * 78)
        print(f"GROUPED BY {gr['group_by']}  -> {gr['n_groups']:,} groups")
        print(f"(showing {len(gr['preview_largest_groups'])} largest groups)")
        print("=" * 78)
        for g in gr["preview_largest_groups"]:
            key_str = ", ".join(f"{k}={v}" for k, v in g["key"].items())
            print(f"\n  {key_str}   (n_rows={g['n_rows']:,})")
            for c, s in g["numeric"].items():
                print(f"      {c:<28} mean={_fmt(s['mean'])}  "
                      f"min={_fmt(s['min'])}  max={_fmt(s['max'])}  "
                      f"std={_fmt(s['std'])}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def default_group_specs(headers):
    """Sensible defaults for the ads dataset; empty otherwise."""
    specs = []
    if "page_id" in headers:
        specs.append(["page_id"])
        if "ad_id" in headers:
            specs.append(["page_id", "ad_id"])
    return specs


def main(argv=None):
    p = argparse.ArgumentParser(description="Pure-Python descriptive statistics.")
    p.add_argument("csv_path", help="Path to the CSV file to analyze.")
    p.add_argument("--group-by", action="append", default=[],
                   help="Comma-separated columns to group by. Repeatable. "
                        "Example: --group-by page_id --group-by page_id,ad_id")
    p.add_argument("--top-n", type=int, default=5,
                   help="Top-N values to show for categorical columns (default 5).")
    p.add_argument("--top-groups", type=int, default=10,
                   help="How many largest groups to print per grouping (default 10).")
    p.add_argument("--out", help="Optional path to write the full report as JSON.")
    args = p.parse_args(argv)

    headers, rows = load_csv(args.csv_path)
    if not headers:
        print("No columns found — is this a valid CSV?", file=sys.stderr)
        return 1

    report = analyze(headers, rows, top_n=args.top_n)

    group_specs = [g.split(",") for g in args.group_by] or default_group_specs(headers)
    group_results = []
    for spec in group_specs:
        missing_cols = [c for c in spec if c not in headers]
        if missing_cols:
            print(f"[warn] skipping group {spec}: missing columns {missing_cols}",
                  file=sys.stderr)
            continue
        group_results.append(grouped_numeric(headers, rows, spec, args.top_groups))

    print_report(args.csv_path, report, group_results)

    if args.out:
        # Drop the bulky 'all_groups' preview duplication-free dump.
        out = {"dataset": args.csv_path, "summary": report,
               "grouped": [{k: v for k, v in gr.items() if k != "preview_largest_groups"}
                           for gr in group_results]}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=str)
        print(f"\n[ok] Full JSON report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
