# Reflection: Pure Python vs Pandas vs Polars

This document answers the research questions from Milestone A, drawing on
my experience building and running all three scripts on the Facebook Ads dataset.

---

## Questions

### Was it hard to get identical numbers across all three approaches? What caused discrepancies?

Honestly, yes — it was harder than I expected. You'd think computing a mean or
a standard deviation would be straightforward, but the devil is in the details.
The discrepancies I ran into fell into three main buckets:

1. **Missing-value conventions.** This was the biggest headache. Pandas, by
   default, has a long built-in list of strings it silently converts to `NaN`
   (`NA`, `N/A`, `null`, empty strings, etc.). Polars only treats values as null
   if you explicitly tell it via `null_values`. And pure Python treats everything
   as a plain string unless you check it yourself. At first, my scripts were
   disagreeing on counts because Pandas was catching missing values the other two
   weren't. The fix was to define one shared NA token set (`""`, `"na"`, `"n/a"`,
   `"nan"`, `"null"`, `"none"`) and apply it identically everywhere — using
   `keep_default_na=False` in Pandas so it wouldn't sneak in extra conversions.

2. **Standard deviation (ddof).** This one bit me early on. Pandas and Polars
   both default to *sample* standard deviation (ddof=1), but if you naively
   write the formula by hand in pure Python you'll probably compute *population*
   std (ddof=0). The numbers look close but they're not identical, especially on
   small groups. I caught this when comparing the grouped stats for a `page_id`
   that only had a handful of ads. The fix was simple: use `statistics.stdev()`
   (not `pstdev()`) in the pure Python script.

3. **Type promotion with nulls.** The `bylines` column in the ads dataset has
   1,009 missing values. Pandas promotes numeric columns with any nulls to
   `float64` (since regular `int64` can't hold NaN), Polars keeps them as
   nullable `Int64`, and my pure Python script just calls them `int`. The
   *labels* on the types differ across the three tools, but the actual computed
   statistics are identical once you exclude nulls consistently. It's a cosmetic
   difference, but it confused me at first when I was comparing outputs side by
   side.

   The columns that specifically caused me trouble were `delivery_by_region` and
   `demographic_distribution`. Both contain Python dict-like strings
   (e.g., `{'Texas': {'spend': 249, 'impressions': 47499}}`). All three tools
   correctly inferred them as strings/categorical, but at first I wasn't sure if
   they'd try to parse them as numbers. They didn't — but it meant those columns
   got treated as categorical with over 141,000 and 215,000 unique values
   respectively, which makes mode and top-5 somewhat meaningless. The mode for
   both was `{}` (the empty dict, 30,989 occurrences), which tells you that about
   12.5% of ads had no region or demographic targeting at all.

### Is one approach easier or more performant? Did you measure?

Yes, I timed them informally on the Facebook Ads dataset (246,745 rows):

| Script | Approximate Wall-Clock Time |
|---|---|
| **Pure Python** | ~4–5 minutes |
| **Pandas** | ~12 seconds |
| **Polars** | ~16 seconds |

The pure Python script is dramatically slower — roughly 20x compared to
Pandas/Polars. This makes sense: it's looping through every row in the
interpreter, building dictionaries by hand for grouping, and calling
`statistics.stdev()` on Python lists. Pandas and Polars do the heavy lifting in
compiled C/Rust code.

Between Pandas and Polars, the difference on this dataset was negligible.
Pandas was actually slightly faster here, probably because the CSV reader is
highly optimized for this kind of tabular data and the dataset isn't large
enough for Polars' multithreading to really shine. On bigger files (millions of
rows), I'd expect Polars to pull ahead.

In terms of **developer experience**:
- **Pandas** was the easiest to get started with — I already knew the API, and
  `df.describe()` gives you a lot out of the box. But its implicit behavior
  (silent type coercion, the index, that massive default NA list) is exactly what
  made cross-tool agreement tricky.
- **Polars** felt stricter and more deliberate. The expression API
  (`pl.col("x").mean()`) reads like a query plan, which I actually liked. It
  forced me to be explicit about what I wanted, and that meant fewer surprises.
- **Pure Python** was the most tedious by far — implementing groupby as a
  `defaultdict(list)` and manually computing stats is a lot of code. But it was
  genuinely educational. I now have a much clearer mental model of what Pandas
  does behind a single `groupby().agg()` call.

At this dataset size (246K rows), the performance difference doesn't matter for a
one-off analysis. But if this were a daily pipeline running on millions of rows,
I'd pick Polars without hesitation.

### What would you tell a junior analyst to learn first?

I'd tell them to **start with pure Python** — but just for a week or two, and
just enough to implement basic operations like reading a CSV, computing a mean
while skipping missing values, and grouping rows into buckets by a key column.
Not because pure Python is the right production tool, but because if you don't
understand what "group by" actually *does* at the row level, Pandas will feel
like magic — and magic breaks in confusing ways.

After that, **learn Pandas**. It's still the lingua franca of data analysis in
Python. Every tutorial, every Stack Overflow answer, every colleague's notebook
uses it. The documentation is enormous, the community is helpful, and most
real-world datasets you'll encounter fit comfortably in memory with Pandas.

Then, once you've hit a wall — maybe a file that's too big, or you're tired of
debugging silent `NaN` propagation, or you need something faster — **pick up
Polars**. It's a genuinely better-designed tool in many ways, and knowing it
makes you a stronger analyst. But it has a smaller community and fewer
tutorials, so it helps to already understand the *concepts* from Pandas first.

### Can AI tools produce useful starter code? Do you agree with their defaults?

To answer this question, I tested a few popular AI coding assistants by asking
them to generate descriptive statistics scripts and compared their output to
what I'd written by hand. Here's what I found:

**What they got right:** The basic structure was solid — they immediately reached
for `df.describe()` in Pandas, `value_counts()` for categorical columns, and
`argparse` for CLI handling. The Polars code used the expression API correctly.
For pure Python, they suggested `csv.DictReader` and `statistics.stdev`, which
are the right choices.

**What was wrong or needed fixing:**
- Every AI tool generated Pandas code using `pd.read_csv()` without
  `keep_default_na=False`. This means Pandas silently treats more strings as NA
  than you might expect, which would cause disagreements with Polars and pure
  Python. None of the tools flagged this as a potential issue.
- The ddof convention was correct in some outputs but not others. One tool used
  `statistics.pstdev()` (population std, ddof=0) instead of `stdev()` (sample
  std, ddof=1), which would produce different numbers than Pandas/Polars.
- Polars API drift was a real problem. Several tools generated code using
  `.apply()` which has been deprecated in newer Polars versions. The expression-
  based API (`.map_elements()` or native expressions) is what you actually need.

**Where I disagreed with their defaults:** When asked for "descriptive
statistics," every AI tool defaulted to just `df.describe()` — which only covers
numeric columns and doesn't show missing values, unique counts, or mode for
categorical columns. A junior analyst following that advice would miss half the
picture. You have to explicitly ask for categorical summaries, missing-value
counts, and grouped analysis.

**Bottom line:** AI tools are useful for boilerplate and getting started quickly,
but you absolutely cannot trust them on the statistical assumptions that matter
for correctness (ddof, NA handling, type inference). The best safeguard is doing
what I did here — building the same analysis in multiple tools and verifying
they agree.

### What cleaning did the complex columns need? Did the three approaches handle this differently?

Several columns in the Facebook Ads dataset contain structured data stored as
strings:

- **`delivery_by_region`**: Contains Python dict-like strings showing spend and
  impressions by state, e.g.,
  `{'Texas': {'spend': 249, 'impressions': 47499}}`. There are 141,122 unique
  values.
- **`demographic_distribution`**: Similar nested dicts broken down by age/gender
  groups, with 215,622 unique values.
- **`publisher_platforms`**: Lists like `['facebook', 'instagram']`.
- **`illuminating_mentions`**: Lists of mentioned political figures like
  `['Kamala Harris', 'Tim Walz']`.

I made the decision to **treat all of these as opaque strings** for the
descriptive statistics. Here's why: parsing and exploding them into normalized
tables would be a whole separate data engineering task — and the assignment is
about descriptive statistics, not data transformation. As strings, we can still
report useful information: the mode for `delivery_by_region` is `{}` (empty
dict, meaning no regional targeting), which is actually meaningful.

All three tools handled this the same way — they all inferred these columns as
strings/categorical and computed count, unique, mode, and top-5 values. There
wasn't really a difference between Pandas, Polars, and pure Python here because
the decision to treat them as strings was made *before* any statistical
computation.

If I were doing a deeper analysis, Pandas would have a slight edge for parsing
these — `ast.literal_eval()` combined with `pd.json_normalize()` or `.explode()`
makes it relatively easy to flatten nested structures. Polars can do it too with
`.map_elements()`, but it's less ergonomic. Pure Python would require writing
the parsing and reshaping entirely by hand.
