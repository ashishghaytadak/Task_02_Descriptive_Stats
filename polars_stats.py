#!/usr/bin/env python3


import argparse
import json
import sys

import polars as pl

_BASE = ["", "na", "n/a", "nan", "null", "none"]
NA_VALUES = sorted({t for b in _BASE for t in (b, b.upper(), b.title())})


def load_csv(path):
    """Read a CSV with standardized null handling. infer_schema_length=None scans the
    whole file so a numeric column isn't mis-typed because of late float values."""
    return pl.read_csv(
        path,
        null_values=NA_VALUES,
        infer_schema_length=None,
        ignore_errors=False,
        truncate_ragged_lines=True,
    )


def is_numeric(dtype):
    try:
        return dtype.is_numeric()
    except AttributeError:
        return dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                         pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                         pl.Float32, pl.Float64)


def column_report(df):
    n = df.height
    report = {
        "row_count": int(n),
        "column_count": int(df.width),
        "inferred_types": {c: str(t) for c, t in df.schema.items()},
        "missing_per_column": {},
        "missing_pct_per_column": {},
        "numeric": {},
        "categorical": {},
    }

    for c in df.columns:
        nulls = int(df[c].null_count())
        report["missing_per_column"][c] = nulls
        report["missing_pct_per_column"][c] = (nulls / n * 100) if n else 0.0

    for c, dt in df.schema.items():
        if is_numeric(dt):
            stats = df.select([
                pl.col(c).count().alias("count"),     # count() excludes nulls
                pl.col(c).mean().alias("mean"),
                pl.col(c).min().alias("min"),
                pl.col(c).max().alias("max"),
                pl.col(c).std().alias("std"),          # ddof=1 by default
                pl.col(c).median().alias("median"),
            ]).row(0, named=True)
            report["numeric"][c] = {k: _none(v) for k, v in stats.items()}
        else:
            s = df[c].drop_nulls().cast(pl.Utf8)
            vc = s.value_counts(sort=True)            # columns: [<c>, "count"]
            val_col = vc.columns[0]
            top = [(str(r[val_col]), int(r["count"]))
                   for r in vc.head(5).iter_rows(named=True)]
            if vc.height:
                first = vc.row(0, named=True)
                mode_val, mode_freq = str(first[val_col]), int(first["count"])
            else:
                mode_val, mode_freq = None, 0
            report["categorical"][c] = {
                "count": int(s.len()),
                "unique": int(df[c].n_unique()),
                "mode": mode_val,
                "mode_freq": mode_freq,
                "top": top,
            }
    return report


def grouped_report(df, group_cols, top_groups=10):
    numeric_cols = [c for c, dt in df.schema.items()
                    if is_numeric(dt) and c not in group_cols]
    n_groups = df.select(group_cols).n_unique()
    if not numeric_cols:
        return {"group_by": group_cols, "n_groups": int(n_groups),
                "numeric_columns": [], "note": "no numeric columns to aggregate"}

    aggs = [pl.len().alias("__n_rows__")]
    for c in numeric_cols:
        aggs += [
            pl.col(c).count().alias(f"{c}__count"),
            pl.col(c).mean().alias(f"{c}__mean"),
            pl.col(c).min().alias(f"{c}__min"),
            pl.col(c).max().alias(f"{c}__max"),
            pl.col(c).std().alias(f"{c}__std"),
            pl.col(c).median().alias(f"{c}__median"),
        ]

    grouped = (df.group_by(group_cols)
                 .agg(aggs)
                 .sort("__n_rows__", descending=True)
                 .head(top_groups))

    preview = {}
    for row in grouped.iter_rows(named=True):
        key = tuple(row[c] for c in group_cols)
        preview[str(key)] = {
            "n_rows": int(row["__n_rows__"]),
            "numeric": {
                c: {stat: _none(row[f"{c}__{stat}"])
                    for stat in ["count", "mean", "min", "max", "std", "median"]}
                for c in numeric_cols
            },
        }
    return {"group_by": group_cols, "n_groups": int(n_groups),
            "numeric_columns": numeric_cols, "preview_largest_groups": preview}


def _none(x):
    return None if x is None else (x.item() if hasattr(x, "item") else x)


def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.4f}"
    return str(x)


def print_report(path, df, report, group_results):
    print("=" * 78)
    print("POLARS DESCRIPTIVE STATISTICS")
    print(f"Dataset: {path}")
    print("=" * 78)
    print(f"Rows: {report['row_count']:,}    Columns: {report['column_count']}")

    print("\n-- Inferred dtypes & missing values ----------------------------------")
    for c in df.columns:
        miss = report["missing_per_column"][c]
        pct = report["missing_pct_per_column"][c]
        print(f"  {c:<32} {report['inferred_types'][c]:<10} "
              f"missing={miss:>8,} ({pct:5.1f}%)")

    print("\n-- Numeric columns ---------------------------------------------------")
    for c, st in report["numeric"].items():
        print(f"\n[{c}]")
        print(f"    count={st['count']:,}  mean={_fmt(st['mean'])}  std={_fmt(st['std'])}")
        print(f"    min={_fmt(st['min'])}  median={_fmt(st['median'])}  max={_fmt(st['max'])}")

    print("\n-- Categorical columns -----------------------------------------------")
    for c, st in report["categorical"].items():
        print(f"\n[{c}]")
        print(f"    count={st['count']:,}  unique={st['unique']:,}  "
              f"mode={st['mode']!r} (freq={st['mode_freq']:,})")
        tops = ", ".join(f"{v!r}:{n}" for v, n in st["top"])
        print(f"    top: {tops}")

    for gr in group_results:
        print("\n" + "=" * 78)
        print(f"GROUPED BY {gr['group_by']}  -> {gr.get('n_groups', '?'):,} groups")
        print("=" * 78)
        for key, g in gr.get("preview_largest_groups", {}).items():
            print(f"\n  {key}   (n_rows={g['n_rows']:,})")
            for col, s in g["numeric"].items():
                print(f"      {col:<28} mean={_fmt(s['mean'])}  min={_fmt(s['min'])}  "
                      f"max={_fmt(s['max'])}  std={_fmt(s['std'])}")


def default_group_specs(df):
    specs = []
    if "page_id" in df.columns:
        specs.append(["page_id"])
        if "ad_id" in df.columns:
            specs.append(["page_id", "ad_id"])
    return specs


def main(argv=None):
    p = argparse.ArgumentParser(description="Polars descriptive statistics.")
    p.add_argument("csv_path")
    p.add_argument("--group-by", action="append", default=[],
                   help="Comma-separated columns. Repeatable.")
    p.add_argument("--top-groups", type=int, default=10)
    p.add_argument("--out", help="Optional JSON output path.")
    args = p.parse_args(argv)

    df = load_csv(args.csv_path)
    report = column_report(df)

    specs = [g.split(",") for g in args.group_by] or default_group_specs(df)
    group_results = []
    for spec in specs:
        missing = [c for c in spec if c not in df.columns]
        if missing:
            print(f"[warn] skipping group {spec}: missing {missing}", file=sys.stderr)
            continue
        group_results.append(grouped_report(df, spec, args.top_groups))

    print_report(args.csv_path, df, report, group_results)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"dataset": args.csv_path, "summary": report,
                       "grouped": group_results}, fh, indent=2, default=str)
        print(f"\n[ok] Full JSON report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
