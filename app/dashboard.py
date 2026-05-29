"""
app/dashboard.py
================
Streamlit dashboard for the NOAA fisheries landings analysis.

Connects to PostgreSQL, runs the analytical SQL from /sql, and visualizes:
  - per-species long-run trend (regression-based classification)
  - year-over-year landings with the fitted trend line
  - state revenue exposure to declining species
  - data-quality transparency (confidentiality suppression rates)

Run:
    streamlit run app/dashboard.py

Connection is read from environment variables (never hard-code credentials):
    PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
"""

import os
import pandas as pd
import plotly.express as px
import streamlit as st

# psycopg2 is imported lazily so the file at least loads for inspection
# even on a machine without a database configured.
try:
    import psycopg2
    HAVE_PG = True
except ImportError:
    HAVE_PG = False

st.set_page_config(page_title="NOAA Fisheries Trends", layout="wide")


@st.cache_resource
def get_connection():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "fisheries"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )


@st.cache_data
def run_query(sql: str) -> pd.DataFrame:
    conn = get_connection()
    return pd.read_sql_query(sql, conn)


# ---- The analytical SQL (kept in sync with /sql/04_trend_regression.sql) ----
TREND_SQL = """
WITH species_year AS (
    SELECT species, year, SUM(pounds) AS total_pounds
    FROM landings
    WHERE NOT is_withheld AND NOT is_aggregate
    GROUP BY species, year
    HAVING SUM(pounds) > 0
),
fit AS (
    SELECT species,
           COUNT(*) AS n_years,
           regr_slope(LN(total_pounds), year) AS log_slope,
           regr_r2(LN(total_pounds), year)    AS r2
    FROM species_year GROUP BY species
)
SELECT species, n_years,
       ROUND((100.0*(EXP(log_slope)-1))::NUMERIC, 1) AS annual_pct_rate,
       ROUND(r2::NUMERIC,3) AS trend_strength_r2,
       CASE
         WHEN EXP(log_slope)-1 <= -0.05 AND r2 >= 0.5 THEN 'DECLINING (clear)'
         WHEN EXP(log_slope)-1 <= -0.02 AND r2 >= 0.5 THEN 'DECLINING (mild)'
         WHEN EXP(log_slope)-1 >=  0.05 AND r2 >= 0.5 THEN 'GROWING (clear)'
         WHEN r2 < 0.5 THEN 'NO CLEAR TREND'
         ELSE 'STABLE'
       END AS classification
FROM fit
WHERE n_years >= 15           -- only species with enough history
ORDER BY annual_pct_rate ASC;
"""

SERIES_SQL = """
SELECT species, year, SUM(pounds) AS total_pounds, SUM(dollars) AS total_dollars
FROM landings
WHERE NOT is_withheld AND NOT is_aggregate
GROUP BY species, year ORDER BY species, year;
"""

WITHHELD_SQL = """
SELECT species,
       COUNT(*) AS total_year_rows,
       COUNT(*) FILTER (WHERE is_withheld) AS withheld_rows,
       ROUND((100.0*COUNT(*) FILTER (WHERE is_withheld)/COUNT(*))::NUMERIC, 1) AS pct_withheld
FROM landings WHERE NOT is_aggregate
GROUP BY species
HAVING COUNT(*) >= 10
ORDER BY pct_withheld DESC;
"""

# ----------------------------- UI -----------------------------
st.title("🐟 U.S. Commercial Fisheries — Landings Trend Explorer")
st.caption(
    "Source: NOAA Fisheries FOSS landings. Landings measure fishing activity "
    "and ex-vessel revenue — not fish population directly. Declines are "
    "signals of stock pressure, quota changes, closures, or market shifts."
)

if not HAVE_PG:
    st.error("psycopg2 not installed. Run: pip install psycopg2-binary")
    st.stop()

try:
    trends = run_query(TREND_SQL)
    series = run_query(SERIES_SQL)
    withheld = run_query(WITHHELD_SQL)
except Exception as e:
    st.error(f"Database error: {e}\n\nDid you run the SQL setup and set PG* env vars?")
    st.stop()

# --- Section 1: trend summary ---
st.subheader("Species trend classification")
c1, c2 = st.columns([2, 3])
with c1:
    st.dataframe(trends, use_container_width=True, hide_index=True)
with c2:
    fig = px.bar(
        trends, x="annual_pct_rate", y="species", orientation="h",
        color="classification", title="Compound annual change in landings (%)",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)

# --- Section 2: drill into one species ---
st.subheader("Per-species history")
pick = st.selectbox("Species", sorted(series["species"].unique()))
sub = series[series["species"] == pick]
fig2 = px.scatter(
    sub, x="year", y="total_pounds", trendline="ols",
    title=f"{pick}: landings (lbs) with fitted trend",
)
st.plotly_chart(fig2, use_container_width=True)

# --- Section 3: data quality ---
st.subheader("Data-quality transparency: confidentiality suppression")
st.caption(
    "High suppression means a species' history has many withheld rows; "
    "treat its trend with extra caution. Showing this is a credibility check."
)
st.dataframe(withheld, use_container_width=True, hide_index=True)
