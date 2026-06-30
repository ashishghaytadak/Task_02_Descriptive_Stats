# Descriptive Statistics: Pure Python vs Pandas vs Polars

Three independent implementations of the same descriptive-statistics analysis,
plus a cross-dataset comparison tool. Built for the 2024 U.S. election social-media
datasets (Facebook Ads, Facebook Posts, Twitter/X Posts), but the scripts are
**dataset-agnostic**: each accepts a CSV path on the command line and adapts to the
schema it finds.



## Files

| File | What it does |
|---|---|
| `pure_python_stats.py` | Descriptive + grouped stats using **only the standard library** (`csv`, `statistics`, `collections`, …). No third-party deps. |
| `pandas_stats.py` | Same analysis using **Pandas** (`describe`, `value_counts`, `nunique`, `groupby`). |
| `polars_stats.py` | Same analysis using **Polars** (expression API, `group_by`, `value_counts`, `n_unique`). |
| `cross_dataset.py` | Milestone B: compares shared columns across multiple datasets and writes `CROSS_DATASET.md`. |
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
# Milestone A — Facebook Ads, default grouping (page_id, then page_id+ad_id)
python pure_python_stats.py data/facebook_ads.csv
python pandas_stats.py      data/facebook_ads.csv
python polars_stats.py      data/facebook_ads.csv

# Milestone B — same scripts, different files & grouping keys
python pandas_stats.py data/facebook_posts.csv --group-by Page_Category
python polars_stats.py data/twitter_posts.csv  --group-by account --out tw.json

# Cross-dataset comparison (writes CROSS_DATASET.md)
python cross_dataset.py data/facebook_ads.csv data/facebook_posts.csv data/twitter_posts.csv
```

If you omit `--group-by`, the scripts auto-apply the ads defaults when `page_id`/
`ad_id` exist, and otherwise skip grouping (pass your own keys after inspecting the
schema — see the assignment's note about choosing sensible grouping columns for
posts and tweets).

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
- **Facebook Posts:** 19,009 rows. Engagement columns like `Total Interactions` are stored as comma-formatted strings (e.g., "268,841") and must be cleaned before numeric analysis.
- **Twitter/X Posts:** 27,304 rows. Engagement distribution is highly skewed, with `viewCount` averaging ~507,000 but reaching up to 333 million, showing extreme viral outliers.
- **Cross-dataset:** Detailed in `CROSS_DATASET.md`; shared illuminating metrics highlight different platform norms. Engagement metrics follow heavy-tailed distributions across all platforms but vary in scale.

## Reproducibility

Clone, install `requirements.txt`, drop the CSVs into `data/`, and run the commands
above. The scripts are deterministic; the same inputs produce the same output.
