# Descriptive Statistics: Pure Python vs Pandas vs Polars

Three independent implementations of the same descriptive-statistics analysis,
including grouped statistics by `page_id` and by `page_id` + `ad_id`.
Built for the 2024 U.S. election Facebook Ads dataset, but the scripts are
**dataset-agnostic**: each accepts a CSV path on the command line and adapts to the
schema it finds.



## Files

| File | What it does |
|---|---|
| `pure_python_stats.py` | Descriptive + grouped stats using **only the standard library** (`csv`, `statistics`, `collections`, …). No third-party deps. |
| `pandas_stats.py` | Same analysis using **Pandas** (`describe`, `value_counts`, `nunique`, `groupby`). |
| `polars_stats.py` | Same analysis using **Polars** (expression API, `group_by`, `value_counts`, `n_unique`). |
| `requirements.txt` | Dependencies for the Pandas/Polars scripts. |
| `REFLECTION.md` | Comparative analysis and answers to the research questions. |



## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # not needed for the pure-Python script
```

## Running

Each script takes a CSV path and optional `--group-by` keys (comma-separated,
repeatable). `--out report.json` dumps the full machine-readable report.

```bash
# Facebook Ads, default grouping (page_id, then page_id+ad_id)
python pure_python_stats.py data/facebook_ads.csv
python pandas_stats.py      data/facebook_ads.csv
python polars_stats.py      data/facebook_ads.csv
```

If you omit `--group-by`, the scripts auto-apply the default groupings (by `page_id`, and then by `page_id` and `ad_id`).

## How the three are kept in agreement

Getting three different tools to produce **identical numbers** takes deliberate
choices. All three scripts:

- Treat the same token set as missing (`""`, `NA`, `N/A`, `NaN`, `null`, `None`,
  case-insensitively). Pandas' large built-in NA list is **disabled**
  (`keep_default_na=False`) so it doesn't silently diverge from the others.
- Use **sample** standard deviation (ddof = 1), which is the Pandas/Polars
  `describe()` default; the pure-Python script uses `statistics.stdev`, not
  `pstdev`, to match.
- Infer numeric vs. categorical from the **values**, so a column counts as numeric
  only when every non-missing value parses as a number.

One intentional, documented difference remains: a numeric column with missing
values is reported as `float64` by Pandas (it has no nullable int by default),
as nullable `Int64` by Polars, and as `int` by the pure-Python script. The
**type label** differs; the computed statistics are identical. This is discussed
in `REFLECTION.md`.

## Summary of findings

- **Facebook Ads:** 246,745 rows. The `bylines` column has notable missing data (1,009 missing). Columns like `delivery_by_region` and `demographic_distribution` contain complex string-formatted dictionaries requiring custom parsing. Spend varies drastically with a long-tail distribution.

## Reproducibility

Clone, install `requirements.txt`, drop the CSVs into `data/`, and run the commands
above. The scripts are deterministic; the same inputs produce the same output.
