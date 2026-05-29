# Decisions Log

This is the most important file in the repo for understanding *why* the
project looks the way it does. Each entry is a real judgment call, the
options considered, and the reasoning. These are the questions an
interviewer is most likely to probe.

---

## D0. The feed mixes Commercial and Recreational — filter to Commercial

When the live API schema was inspected, rows carried a `collection` field
("Commercial" / "Recreational") and a `source` field (e.g. "MRIP" for the
recreational survey program). Recreational rows have NULL `dollars` because
recreational fishing generates no ex-vessel revenue.

This project is about *commercial* fisheries. Mixing in recreational rows
would (a) corrupt every revenue figure with NULLs and (b) conflate two
fundamentally different activities in the pounds totals.

**Decision:** The clean step filters `WHERE collection = 'Commercial'`. The
validation harness explicitly checks that 100% of recreational rows are
dropped. This was discovered by inspecting the real API response, not
assumed up front — a reminder to always look at the actual data first.

---

## D1. "Port" / state means the LANDING location, not the catch location

NOAA's own caveat: landings data record where fish *first crossed the dock
or were reported from*, not where they were harvested. A spike or drop at a
given state can reflect where boats chose to *sell*, not where fish live.

**Decision:** Name the column for what it is (landing/sale location) and
frame all findings as activity/revenue at the point of sale. Never imply a
geographic harvest map.

---

## D2. A withheld value is NULL, not zero

NOAA suppresses species-level rows that would identify an individual dealer
("WITHHELD FOR CONFIDENTIALITY"). If you coerce those blanks to `0`, every
confidential year looks like a total collapse, and the decline detector
fills with false alarms.

**Decision:** Store withheld pounds/dollars as `NULL`, flag the row
(`is_withheld`), and exclude withheld rows from trend math. Surface the
suppression rate per species so users know where the data is thin.

---

## D3. Exclude "...UNCLASSIFIED" aggregate rows from per-species analysis

Rows like "FINFISHES, UNCLASSIFIED" are sums of species NOAA couldn't
attribute individually. Treating them as a species double-counts and
pollutes per-species trends.

**Decision:** Flag aggregates (`is_aggregate`) and exclude them from
species-level analysis. They could still be used for an all-species total,
but not for per-species trends.

---

## D4. Landings are NOT population — frame as a signal, not a verdict

A drop in landings can mean: fewer fish, a lower quota, a fishery closure,
boats fishing elsewhere, or a price/market change. The data cannot, on its
own, prove a stock is collapsing — let alone "extinct."

**Decision:** Report declining *landings/revenue* as a **signal of possible
stock pressure**, and recommend cross-referencing NOAA's official stock-
status ("overfished"/"overfishing") designations before drawing conclusions.
Defensible beats dramatic.

---

## D5. Do the analysis in SQL, not pandas

The point of the project is to demonstrate SQL. It would be easy to `SELECT *`
and do everything in pandas, but then the SQL is trivial.

**Decision:** Year-over-year change (`LAG`), endpoint trends (`ROW_NUMBER` +
`FILTER`), revenue-at-risk share, and the regression trend (`regr_slope`,
`regr_r2`) are all computed *in the database*. pandas/Plotly only visualize.

---

## D6. Switched from fixed-threshold trend to log-linear regression

**First approach:** compare first-3-year average vs last-3-year average,
flag if the drop exceeds a fixed % threshold.

**Problem found during validation:** over a 20+ year window, a species
drifting down ~1%/yr from noise alone crosses a 5% endpoint threshold, so
genuinely-stable species (BROWN SHRIMP, PACIFIC SALMON in the test data)
got mislabeled as declining. The threshold conflates slow drift with real
decline.

**Fix:** fit a linear regression of `LN(pounds)` on `year`. The slope is a
compound annual rate; pair it with R² (trend strength). A species is only
"declining" if the rate is meaningfully negative AND the trend is reasonably
consistent (R² ≥ 0.5). This eliminated the false positives and recovered the
true planted rates within ~1 pt.

**Why log:** regressing the log makes the slope a *proportional* rate
(comparable across big and small fisheries) instead of an absolute pounds/yr
that favors large fisheries.

---

## D7. Synthetic data for development, real API for production

The dev environment couldn't reach NOAA's network, so the analysis was
developed against a structurally-faithful synthetic dataset with *planted
ground truth* (known declining/stable/growing species). This let me prove
the queries detect what they should and ignore what they shouldn't.

**Decision:** Ship both `fetch_noaa_data.py` (real FOSS REST API) and
`generate_synthetic_data.py` (validation fixture). The schema and SQL are
identical for both; only the data source swaps. The validation harness
(`validate.py`) checks the logic against ground truth.

---

## D8. Credentials from environment, never hard-coded

Connection details come from `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD`
environment variables. No secrets in the repo.
