#!/usr/bin/env python3
"""
pandas_stats.py
===============
Descriptive statistics + grouped analysis using Pandas.

Generalized (Milestone B) version: accepts any CSV via the command line and adapts
to its schema. Also covers Milestone A when pointed at the Facebook Ads file.

The missing-value tokens and sample-std convention are chosen to MATCH
pure_python_stats.py and polars_stats.py so the three tools agree numerically.

Usage
-----
    python pandas_stats.py <path_to_csv>
    python pandas_stats.py ads.csv --group-by page_id --group-by page_id,ad_id
    python pandas_stats.py posts.csv --group-by Page_Category --out report.json
"""

import argparse
import json
import sys

import pandas as pd


_BASE = ["", "na", "n/a", "nan", "null", "none"]
NA_VALUES = sorted({t for b in _BASE for t in (b, b.upper(), b.title())})


def load_csv(path):
    """Read a CSV with our standardized missing-value handling."""
    return pd.read_csv(
        path,
        na_values=NA_VALUES,
        keep_default_na=False,
        dtype=None,            # let pandas infer types from values
        low_memory=False,
    )


def column_report(df):
    """Per-column stats split into numeric vs non-numeric, plus dataset-level info."""
    report = {
        "row_count": int(len(df)),
        "column_count": int(df.shape[1]),
        "inferred_types": {c: str(t) for c, t in df.dtypes.items()},
        "missing_per_column": {c: int(df[c].isna().sum()) for c in df.columns},
        "missing_pct_per_column": {
            c: float(df[c].isna().mean() * 100) for c in df.columns
        },
        "numeric": {},
        "categorical": {},
    }

    numeric_cols = df.select_dtypes(include="number").columns
    other_cols = [c for c in df.columns if c not in numeric_cols]

    # Numeric: count, mean, min, max, std (ddof=1 default), median
    for c in numeric_cols:
        s = df[c]
        report["numeric"][c] = {
            "count": int(s.count()),
            "mean": _none(s.mean()),
            "min": _none(s.min()),
            "max": _none(s.max()),
            "std": _none(s.std()),       # sample std, ddof=1 -> matches the other scripts
            "median": _none(s.median()),
        }

    # Non-numeric: count, unique, mode + freq, top 5
    for c in other_cols:
        s = df[c].dropna().astype(str)
        vc = s.value_counts()
        if len(vc):
            mode_val, mode_freq = vc.index[0], int(vc.iloc[0])
            top = [(str(idx), int(cnt)) for idx, cnt in vc.head(5).items()]
        else:
            mode_val, mode_freq, top = None, 0, []
        report["categorical"][c] = {
            "count": int(s.shape[0]),
            "unique": int(df[c].nunique(dropna=True)),
            "mode": mode_val,
            "mode_freq": mode_freq,
            "top": top,
        }
    return report


def grouped_report(df, group_cols, top_groups=10):
    """groupby(group_cols) aggregations over numeric columns (keys excluded)."""
    numeric_cols = [c for c in df.select_dtypes(include="number").columns
                    if c not in group_cols]
    if not numeric_cols:
        return {"group_by": group_cols, "n_groups": int(df.groupby(group_cols).ngroups),
                "numeric_columns": [], "note": "no numeric columns to aggregate"}

    g = df.groupby(group_cols, dropna=False)
    agg = g[numeric_cols].agg(["count", "mean", "min", "max", "std", "median"])
    sizes = g.size().sort_values(ascending=False)
    preview_keys = sizes.head(top_groups).index

    preview = {}
    for key in preview_keys:
        preview[str(key)] = {
            "n_rows": int(sizes.loc[key]),
            "numeric": {
                col: {stat: _none(agg.loc[key, (col, stat)])
                      for stat in ["count", "mean", "min", "max", "std", "median"]}
                for col in numeric_cols
            },
        }
    return {
        "group_by": group_cols,
        "n_groups": int(g.ngroups),
        "numeric_columns": numeric_cols,
        "preview_largest_groups": preview,
    }


def _none(x):
    """Convert pandas NaN to None for clean JSON; pass through finite numbers."""
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(x, "item"):
        return x.item()
    return x


def print_report(path, df, report, group_results):
    print("=" * 78)
    print("PANDAS DESCRIPTIVE STATISTICS")
    print(f"Dataset: {path}")
    print("=" * 78)
    print(f"Rows: {report['row_count']:,}    Columns: {report['column_count']}")

    print("\n-- Inferred dtypes & missing values ----------------------------------")
    for c in df.columns:
        miss = report["missing_per_column"][c]
        pct = report["missing_pct_per_column"][c]
        print(f"  {c:<32} {report['inferred_types'][c]:<10} "
              f"missing={miss:>8,} ({pct:5.1f}%)")

    print("\n-- Numeric columns (describe) ----------------------------------------")
    num_cols = df.select_dtypes(include="number").columns
    if len(num_cols):
        with pd.option_context("display.width", 120, "display.max_columns", 20):
            print(df[num_cols].describe().T.to_string())

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


def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:,.4f}"
    return str(x)


def default_group_specs(df):
    specs = []
    if "page_id" in df.columns:
        specs.append(["page_id"])
        if "ad_id" in df.columns:
            specs.append(["page_id", "ad_id"])
    return specs


def main(argv=None):
    p = argparse.ArgumentParser(description="Pandas descriptive statistics.")
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
