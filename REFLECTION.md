# Reflection: Pure Python vs Pandas vs Polars

This document answers the research questions from both milestones, drawing on
my experience building and running all three scripts across the Facebook Ads,
Facebook Posts, and Twitter/X Posts datasets.

---

## Milestone A questions

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

   `Total Interactions` in the Facebook Posts dataset was another surprise — it
   looks numeric, but it contains comma-formatted numbers like `"268,841"` which
   all three tools correctly identified as strings rather than numbers. That's
   actually the right call since you shouldn't silently strip commas.

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

The `Total Interactions` column in Facebook Posts was another interesting case —
it contains comma-formatted numbers like `"268,841"` that look numeric but are
actually strings. All three scripts correctly identified it as categorical. To
use it as a number, you'd need to strip the commas first (`str.replace(",", "")`),
which is easy in all three tools but has to be done explicitly.

---

## Milestone B questions

### How much Milestone A code survived unchanged? What broke?

The core architecture survived well — about 80-90% of the code carried over
without modification. The parts that survived:
- CLI argument parsing (file path as a positional argument)
- Value-based type inference (checking if every non-missing value parses as a
  number)
- The statistical functions themselves (mean, std, median, etc.)
- Missing-value detection using the shared NA token set
- Output formatting

What **broke** when I pointed the scripts at the Facebook Posts and Twitter
datasets:

1. **Default grouping keys.** The Milestone A code defaulted to grouping by
   `page_id` and `page_id + ad_id`, which don't exist in the posts or tweets
   datasets. The fix was adding the `--group-by` CLI flag and only applying the
   default when those columns actually exist. For posts I used `Page Category`
   (6 groups: PERSON, ACTOR, POLITICIAN, etc.) and for Twitter I used `source`
   (14 groups: Twitter Web App, Twitter for iPhone, etc.).

2. **Column name assumptions.** The Facebook Posts dataset has spaces in column
   names (`Page Category`, `Post Created Date`, `Total Interactions`), which
   tripped up some of my early formatting code that assumed short, snake_case
   names. The print formatting needed wider column widths.

3. **The `Total Interactions` column** in Facebook Posts looks numeric but
   contains comma-formatted strings. My Milestone A code would have tried to
   treat it as a number and either crashed or silently dropped values. The
   value-based type inference correctly caught this — it tries `int()` then
   `float()`, and `"268,841"` fails both, so it's treated as a string.

4. **Column count differences.** Facebook Ads has 41 columns, Posts has 56, and
   Twitter has 47. The output formatting had to adapt to variable-width tables
   rather than assuming a fixed layout.

The main lesson: **anything hardcoded will break.** Column names, column counts,
even assumptions about what "numeric" looks like. The value-based inference
approach is much more robust than hardcoding schemas.

### What made the code dataset-agnostic?

Three key design decisions:

1. **The input file is a CLI argument, never hardcoded.** You can point any of
   the three scripts at any CSV and get results.
2. **Types are inferred from values, not assumed.** Instead of hardcoding
   "column X is numeric," the code checks whether every non-missing value in a
   column actually parses as a number. This means it adapts automatically to
   whatever schema it finds.
3. **Grouping columns are configurable via `--group-by`.** The default only
   applies the ads-specific grouping (`page_id`, `page_id+ad_id`) when those
   columns happen to exist. For any other dataset, you pass your own keys.

### Did the platforms tell the same story on shared columns?

Running `cross_dataset.py` revealed that all three datasets share **27 binary
indicator columns** — the "illuminating" topic and message-type flags. These are
0/1 flags indicating whether a post/ad touches on a given topic or uses a
particular messaging strategy. Here's what stood out:

**Messaging strategy differs sharply between ads and organic content:**
- **Call-to-action (CTA) messaging** was present in 57% of Facebook Ads but only
  13% of Facebook Posts and 11% of Twitter posts. This makes sense — ads are
  designed to drive action; organic posts are more about engagement.
- **Fundraising CTAs** were 23% in ads vs. just 2% in posts and 1% in tweets.
  Ads are literally asking for money; organic content rarely does.
- **Voting CTAs** followed the same pattern: 14% in ads vs. 2% in posts/tweets.

**Topics are more consistent across platforms:**
- **Economy** was discussed at similar rates: 12% in ads, 9% in posts, 16% in
  tweets. Twitter had slightly more economy talk.
- **Immigration** was highest on Twitter (6.5%) compared to ads (3.4%) and posts
  (4.1%) — possibly because Twitter's format encourages more direct political
  commentary.
- **Health** was notably higher in ads (11%) than posts (5%) or tweets (6%),
  likely because health policy (especially abortion/reproductive rights) was a
  major campaign ad topic.

**Incivility** was fairly consistent: 19% in ads, 13% in posts, 18% in tweets.
Interestingly, *ads* were slightly more incivil than organic posts — attack ads
are a real thing.

The three datasets don't share any non-numeric columns, so there was no way to
directly compare things like engagement metrics across platforms. The ads
dataset has `estimated_spend` and `estimated_impressions`; Posts has `Likes`,
`Comments`, `Shares`; Twitter has `likeCount`, `retweetCount`, `viewCount`. These
measure fundamentally different things and can't be compared directly.

### What would a colleague change to analyze a totally different dataset?

Honestly? Very little. They'd just need to:
1. Point the script at their CSV file: `python pandas_stats.py their_data.csv`
2. Choose sensible `--group-by` keys for their domain:
   `--group-by department` or `--group-by region,product`

The type inference, missing-value handling, and per-column statistics "just work"
on any well-formed CSV. What *wouldn't* transfer is **domain knowledge** — knowing
that `page_id` identifies an advertiser, that high `estimated_spend` means a
well-funded campaign, or that `incivility_illuminating = 1` means the content is
uncivil. The scripts compute numbers; interpreting them still requires a human
who understands the data.

The one technical thing that might need tweaking: columns with embedded
structured data (like the region/demographic dicts in the ads file). The scripts
treat those as strings, which is safe but limits the analysis. A colleague with
JSON or nested data would need to add a parsing step before running the stats.

### How has your opinion of the three tools evolved across the tasks?

My views genuinely shifted through this project:

**Pure Python:** I started thinking of this as the "boring homework assignment"
approach, but I came out with real respect for it. Implementing `groupby` as a
`defaultdict(list)` and manually looping through rows to compute stats forced me
to understand exactly what's happening at every step. When the other two scripts
disagreed on a number, I could always go back to the pure Python version and
trace through the logic line by line. It's painfully slow (5 minutes vs. 12
seconds on the ads file), but as a learning tool, nothing beats it.

**Pandas:** I started here — it's what I was most comfortable with. But this
project exposed its rough edges. The silent NA handling with `keep_default_na`
caused real discrepancies I had to hunt down. The index system adds complexity
that isn't always useful. And `describe()` only covers numeric columns by
default, which I always forget. That said, it's still incredibly productive for
exploratory work, and the ecosystem (plotting, IO, integration with everything)
is unmatched.

**Polars:** This was the biggest surprise. I started skeptical — "why learn
another DataFrame library?" — but the expression API grew on me fast. Writing
`pl.col("spend").mean().alias("avg_spend")` feels more deliberate than Pandas'
chained method calls. It forced me to think about what I wanted *before* I wrote
it, which meant fewer bugs. The strict type system and explicit null handling
made cross-tool agreement much easier. And on larger data, the performance
advantage would be significant.

If I had to pick one for a production pipeline today, I'd probably choose Polars.
For a quick one-off exploration in a Jupyter notebook, Pandas. And I'm genuinely
glad I built the pure Python version — I'll never take `df.groupby()` for
granted again.

### Can AI tools handle the generalization problem, or do they default to dataset-specific code?

I tested this specifically by prompting a couple of AI coding assistants with
different levels of specificity and comparing the code they produced.

When I asked for "descriptive statistics on a CSV" and mentioned the ads dataset,
the tools immediately generated code with hardcoded column names — `page_id`,
`ad_id`, `estimated_spend`. They assumed one specific schema and baked it in.
That code would crash the moment you point it at the posts or tweets file.

When I rephrased the prompt to "a script that works on *any* well-formed CSV,"
the output improved — the tools switched to iterating over `df.columns`,
inferring types dynamically, and using CLI arguments for the file path. But
there were still subtle problems:
- They defaulted to treating all numeric-looking columns as numeric, without
  considering that comma-formatted strings like `"268,841"` would fail.
- They didn't think about configurable grouping keys — the generated code either
  skipped grouping entirely or used a hardcoded list of columns.
- Error handling for when a grouping column doesn't exist in a given dataset was
  missing entirely.

The key takeaway: **AI tools default to the specific case, not the general one.**
They can generate working code for *one* dataset quickly, but making code truly
dataset-agnostic requires human judgment about edge cases, type inference
strategies, and configurable parameters. In my estimation, AI gets about 70-80%
of the way there; the last 20% — the part that makes it robust across different
datasets — requires careful thought, testing on multiple inputs, and an
understanding of the failure modes that only come from experience.

The tools are good at boilerplate (argument parsing, file I/O, output formatting,
basic computations), but the design decisions that matter for correctness and
generalization still require a human in the loop.
