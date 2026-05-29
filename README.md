# U.S. Commercial Fisheries — Landings Trend Analysis 🐟

A PostgreSQL + Streamlit project that analyzes NOAA commercial fisheries
landings data to surface species and fishing economies showing multi-year
**declining-catch signals** — the kind of trend consistent with stock
pressure or overfishing.

> **Framing matters:** Landings measure fishing *activity and ex-vessel
> revenue*, not fish population. A decline is a **signal** that warrants
> cross-referencing NOAA's official stock-status designations — not a
> standalone verdict that a stock is collapsing. See
> [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## What it does

- Ingests NOAA FOSS landings (real REST API) into PostgreSQL
- Cleans the data with care for two real-world quirks: confidentiality-
  withheld rows (kept as `NULL`, not `0`) and "...UNCLASSIFIED" aggregate
  rollups (excluded from per-species analysis)
- Computes, **entirely in SQL**:
  - year-over-year change per species (`LAG` window function)
  - long-run trend via log-linear regression (`regr_slope`, `regr_r2`)
  - state revenue exposure to declining species (CTE chain + share-of-total)
  - per-species confidentiality suppression rate (data-quality transparency)
- Visualizes everything in a Streamlit dashboard

---

## Tech stack

PostgreSQL · SQL (window functions, CTEs, regression aggregates) · Python ·
pandas · Plotly · Streamlit

---

## Quick start

```bash
# 1. install deps
pip install -r requirements.txt

# 2a. get real NOAA data (run from a machine with internet)
python scripts/fetch_noaa_data.py
#  --- OR ---
# 2b. generate the validation fixture (no network needed)
python scripts/generate_synthetic_data.py

# 3. point at your Postgres instance
export PGHOST=localhost PGDATABASE=fisheries PGUSER=postgres PGPASSWORD=yourpw

# 4. load + build the schema
python scripts/load_to_postgres.py

# 5. run the dashboard
streamlit run app/dashboard.py
```

To validate the analytical logic against known ground truth (no Postgres
needed):

```bash
python scripts/validate.py
```

---

## Repo layout

```
sql/
  01_schema.sql            schema (raw staging + clean analysis table)
  02_clean.sql             raw -> clean transform (the NULL-vs-0 decision)
  03_analysis.sql          YoY, endpoint trend, revenue-at-risk, data quality
  04_trend_regression.sql  statistically-grounded trend detection
scripts/
  fetch_noaa_data.py       pulls the real NOAA FOSS REST API
  generate_synthetic_data.py  faithful fixture w/ planted ground truth
  load_to_postgres.py      COPY load + runs the SQL setup
  validate.py              asserts the logic detects known trends
app/
  dashboard.py             Streamlit UI
docs/
  DECISIONS.md             every analytical judgment, defended
  INTERVIEW_PREP.md        likely questions + the hardest ones
```

---

## Key findings (on the validation fixture)

The regression detector recovers planted trends within ~1 percentage point
and correctly separates real declines from noise:

| Species | Annual rate | R² | Classification |
|---|---|---|---|
| Bay scallop | −12.0% | 0.998 | Declining (clear) |
| Pacific sardine | −10.0% | 0.996 | Declining (clear) |
| Atlantic cod | −7.0% | 0.990 | Declining (clear) |
| Albacore tuna | +0.3% | 0.183 | No clear trend |
| American lobster | +4.3% | 0.977 | Growing |

(Replace with real-data findings after running `fetch_noaa_data.py`.)

---

## Notes on data

NOAA FOSS landings: <https://www.fisheries.noaa.gov/foss>. Non-confidential
data is public and requires no API key. The live REST endpoint is
`https://apps-st.fisheries.noaa.gov/ods/foss/landings/` (NOAA migrated ODS
to the cloud in 2025; the old `st.nmfs.noaa.gov/ords` host is retired).

Two caveats drive the data-cleaning decisions: (1) the feed mixes commercial
and recreational landings, so this analysis filters to commercial only; and
(2) landings are recorded at the point of *sale/landing*, not harvest, and
species-level values may be suppressed for confidentiality (kept as NULL,
never 0). See [`docs/DECISIONS.md`](docs/DECISIONS.md).
