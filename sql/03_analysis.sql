-- ============================================================
-- 03_analysis.sql  —  The analytical core (the part recruiters read)
-- ============================================================
-- Every query here is intentionally written to do the analytical work in
-- SQL (window functions, CTEs, ranking) rather than pulling raw rows into
-- pandas. That is the whole point of the project.
--
-- IMPORTANT FRAMING: NOAA landings measure FISHING ACTIVITY & REVENUE, not
-- fish population. A decline in landings is a SIGNAL that may reflect stock
-- pressure, quota cuts, closures, or market shifts. We surface signals; we
-- do not claim to "detect extinction." Defensible > dramatic.
-- ============================================================


-- ------------------------------------------------------------
-- Q1. Year-over-year change in landings, per species.
--     Uses LAG() to compare each year to the prior year.
--     Excludes withheld and aggregate rows so comparisons are valid.
-- ------------------------------------------------------------
WITH species_year AS (
    SELECT
        species,
        year,
        SUM(pounds)  AS total_pounds,
        SUM(dollars) AS total_dollars
    FROM landings
    WHERE NOT is_withheld
      AND NOT is_aggregate
    GROUP BY species, year
)
SELECT
    species,
    year,
    total_pounds,
    LAG(total_pounds) OVER (PARTITION BY species ORDER BY year) AS prev_year_pounds,
    ROUND(
        100.0 * (total_pounds - LAG(total_pounds) OVER (PARTITION BY species ORDER BY year))
        / NULLIF(LAG(total_pounds) OVER (PARTITION BY species ORDER BY year), 0),
        1
    ) AS yoy_pct_change
FROM species_year
ORDER BY species, year;


-- ------------------------------------------------------------
-- Q2. Long-run trend per species: compare the most recent 3-year
--     average to the earliest 3-year average in the dataset.
--     This smooths single-year volatility (the "noise") and isolates
--     durable direction (the "signal").
-- ------------------------------------------------------------
WITH species_year AS (
    SELECT species, year, SUM(pounds) AS total_pounds
    FROM landings
    WHERE NOT is_withheld AND NOT is_aggregate
    GROUP BY species, year
),
ranked AS (
    SELECT
        species, year, total_pounds,
        ROW_NUMBER() OVER (PARTITION BY species ORDER BY year ASC)  AS yr_asc,
        ROW_NUMBER() OVER (PARTITION BY species ORDER BY year DESC) AS yr_desc
    FROM species_year
),
endpoints AS (
    SELECT
        species,
        AVG(total_pounds) FILTER (WHERE yr_asc  <= 3) AS early_avg,
        AVG(total_pounds) FILTER (WHERE yr_desc <= 3) AS recent_avg
    FROM ranked
    GROUP BY species
)
SELECT
    species,
    ROUND(early_avg)  AS early_3yr_avg_lbs,
    ROUND(recent_avg) AS recent_3yr_avg_lbs,
    ROUND(100.0 * (recent_avg - early_avg) / NULLIF(early_avg, 0), 1) AS pct_change,
    CASE
        WHEN recent_avg < early_avg * 0.80 THEN 'STRONG DECLINE'
        WHEN recent_avg < early_avg * 0.95 THEN 'DECLINE'
        WHEN recent_avg > early_avg * 1.20 THEN 'STRONG GROWTH'
        WHEN recent_avg > early_avg * 1.05 THEN 'GROWTH'
        ELSE 'STABLE'
    END AS trend_label
FROM endpoints
ORDER BY pct_change ASC;   -- worst declines first


-- ------------------------------------------------------------
-- Q3. Rank states by how much of their landings revenue is
--     concentrated in declining species (a portfolio-risk view:
--     which fishing economies are most exposed?).
--     Uses a CTE chain + window SUM for share-of-total.
-- ------------------------------------------------------------
WITH species_year AS (
    SELECT species, state, year, SUM(pounds) AS total_pounds, SUM(dollars) AS total_dollars
    FROM landings
    WHERE NOT is_withheld AND NOT is_aggregate
    GROUP BY species, state, year
),
species_trend AS (   -- reuse the Q2 endpoint logic to label each species
    SELECT species,
           AVG(total_pounds) FILTER (WHERE yr_asc  <= 3) AS early_avg,
           AVG(total_pounds) FILTER (WHERE yr_desc <= 3) AS recent_avg
    FROM (
        SELECT species, year, SUM(total_pounds) AS total_pounds,
               ROW_NUMBER() OVER (PARTITION BY species ORDER BY year ASC)  AS yr_asc,
               ROW_NUMBER() OVER (PARTITION BY species ORDER BY year DESC) AS yr_desc
        FROM species_year GROUP BY species, year
    ) z
    GROUP BY species
),
state_recent_rev AS (  -- most-recent-year revenue by state & species
    SELECT sy.state, sy.species, sy.total_dollars,
           (st.recent_avg < st.early_avg * 0.95) AS is_declining
    FROM species_year sy
    JOIN species_trend st ON st.species = sy.species
    WHERE sy.year = (SELECT MAX(year) FROM species_year)
)
SELECT
    state,
    ROUND(SUM(total_dollars))                                              AS total_revenue,
    ROUND(SUM(total_dollars) FILTER (WHERE is_declining))                  AS declining_revenue,
    ROUND(100.0 * SUM(total_dollars) FILTER (WHERE is_declining)
          / NULLIF(SUM(total_dollars), 0), 1)                             AS pct_revenue_at_risk
FROM state_recent_rev
GROUP BY state
ORDER BY pct_revenue_at_risk DESC NULLS LAST;


-- ------------------------------------------------------------
-- Q4. Data-quality transparency: how much of each species' history
--     is withheld for confidentiality? High suppression = treat that
--     species' trend with caution. Showing this is a credibility signal.
-- ------------------------------------------------------------
SELECT
    species,
    COUNT(*)                                  AS total_year_rows,
    COUNT(*) FILTER (WHERE is_withheld)        AS withheld_rows,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_withheld) / COUNT(*), 1) AS pct_withheld
FROM landings
WHERE NOT is_aggregate
GROUP BY species
ORDER BY pct_withheld DESC;
