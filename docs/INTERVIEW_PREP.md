# Interview Prep — Fisheries Trend Project

Know this project cold. The artifact isn't the differentiator; your ability
to defend it is. Below are the questions you're most likely to get, grouped
by theme, with the gist of a strong answer. Practice saying these out loud.

---

## SQL / technical

**"Walk me through the hardest query."**
The regression trend (`04_trend_regression.sql`). I aggregate to species-year
totals in a CTE, filter out withheld and aggregate rows, then use Postgres'
`regr_slope` and `regr_r2` aggregates to fit `LN(pounds)` against `year`. The
slope becomes a compound annual rate via `EXP(slope)-1`; R² tells me how
consistent the trend is. A CASE expression turns those two numbers into a
label. Doing it as aggregates means the whole fit happens in one pass in the
DB.

**"Why window functions instead of self-joins for year-over-year?"**
`LAG(...) OVER (PARTITION BY species ORDER BY year)` reads the prior year in
a single scan. A self-join on `year = year-1` does the same thing but scans
the table twice and gets messy with gaps in the year sequence. The window
function is clearer and faster.

**"Why log-transform before regression?"**
So the slope is a *proportional* rate, comparable across a 400k-lb fishery
and an 8M-lb one. A raw linear slope is in pounds/year and structurally
favors big fisheries. Log makes "−7%/yr" mean the same thing everywhere.

**"How would this scale to the full national dataset?"**
Indexes on (species), (year), (state) cover the group-bys. If it grew large
I'd pre-aggregate species-year totals into a materialized view and refresh on
load, so the dashboard hits a small summary table instead of the full grain.

---

## Data quality / judgment (the differentiators)

**"What's the biggest limitation of this analysis?"**
Landings measure fishing activity and revenue, not fish population. A decline
can be a quota cut, a closure, boats selling elsewhere, or a market shift —
not necessarily fewer fish. That's why I frame results as *signals* and
recommend cross-referencing NOAA's official overfished/overfishing stock
status before concluding anything about a stock.

**"How did you handle missing data?"**
NOAA withholds some species-level rows for confidentiality. Critically, those
aren't zeros — they're unknowns. I store them as NULL, flag them, exclude
them from trend math, and report each species' suppression rate so a reader
knows where the history is thin.

**"Tell me something you only learned by looking at the real data."**
My initial schema assumed the feed was all commercial landings. When I
inspected the live API response, the rows had a `collection` field and many
were *recreational* (from the MRIP survey program) with NULL dollar values.
If I'd loaded blindly, my revenue analysis would have been full of nulls and
my pounds totals would have conflated commercial and recreational fishing. I
added a `WHERE collection = 'Commercial'` filter and a validation check that
confirms every recreational row is dropped. The lesson: inspect the actual
payload before trusting your assumptions about a schema.

**"Tell me about a bug or wrong turn."** (Use this — it's your best story.)
My first trend test compared the first 3 years' average to the last 3 years'
and flagged a fixed % drop. Validation against data with known trends showed
it false-flagged stable species, because over 20+ years even tiny noise drift
crosses a fixed threshold. I switched to a log-linear regression judged on
both slope and R², which killed the false positives and recovered the true
rates. It taught me that endpoint comparisons are fragile over long windows.

**"How do you know your results are right?"**
I built a validation harness with planted ground truth — synthetic species
with known declining/stable/growing trends — and asserted the queries detect
all the real declines, avoid false alarms, treat withheld as NULL, and
exclude aggregates. The logic is tested, not just eyeballed.

---

## AI use (be honest and specific)

**"Did you use AI to build this?"**
Yes — I used it to scaffold the ETL and the boilerplate. The parts I own are
the analytical decisions: catching the withheld-as-zero trap, excluding the
unclassified rollups, and especially diagnosing why the fixed-threshold trend
over-flagged and replacing it with the regression approach. AI writes a query
fast; it doesn't know which query is the *right* one for this data's quirks.
My job was directing it and verifying the output against ground truth.

---

## Three hardest questions someone could ask (rehearse these)

1. **"Your R² ≥ 0.5 cutoff is arbitrary — defend it."**
   It is a judgment threshold, not a law. I chose it to require that a trend
   explain at least half the year-to-year variance before I call it a trend;
   below that, wobble dominates. I'd happily show sensitivity to 0.4 / 0.6,
   and in production I'd report the slope's p-value alongside R² rather than a
   single hard cutoff.

2. **"If landings dropped because of a quota, your model calls it a decline.
   Isn't that just wrong?"**
   The *landings* genuinely did decline — that part is correct. What I must
   not do is attribute the cause. That's exactly why the project reports the
   signal and defers causation to the stock-status data. Conflating the two
   would be the real error.

3. **"You developed on synthetic data. How do I trust it works on the real
   NOAA feed?"**
   The schema and SQL are identical for both sources; only the loader changes.
   The synthetic set reproduces NOAA's real quirks (withheld rows, unclassified
   rollups, landing-vs-catch). And the logic is validated against known ground
   truth, which you can't do on real data because you don't know the "right"
   answer in advance. Running `fetch_noaa_data.py` swaps in the live feed with
   no query changes.
