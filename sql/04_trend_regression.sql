-- ============================================================
-- 04_trend_regression.sql  —  Statistically-grounded trend detection
-- ============================================================
-- WHY THIS EXISTS (key interview story):
-- The naive "compare first 3 years vs last 3 years" test (Q2) over-flags.
-- Across a 20+ year window, even a species drifting down 1%/yr by noise
-- crosses a fixed 5% threshold, producing false "declines".
--
-- Fix: fit a linear trend of log(pounds) on year and judge species by the
-- SLOPE (compound annual rate) plus the correlation strength (R). This
-- distinguishes a real directional trend from year-to-year wobble.
--
-- Postgres has the regression aggregates built in:
--   regr_slope(y, x), regr_r2(y, x), corr(y, x)
-- We regress LN(pounds) on year so the slope is ~ a continuous growth rate
-- (e.g. slope -0.07 ≈ -7%/yr).
-- ============================================================

WITH species_year AS (
    SELECT species, year, SUM(pounds) AS total_pounds
    FROM landings
    WHERE NOT is_withheld AND NOT is_aggregate
    GROUP BY species, year
    HAVING SUM(pounds) > 0           -- LN() needs positive input
),
fit AS (
    SELECT
        species,
        COUNT(*)                                  AS n_years,
        regr_slope(LN(total_pounds), year)        AS log_slope,   -- ≈ annual rate
        regr_r2(LN(total_pounds), year)           AS r2           -- trend strength 0..1
    FROM species_year
    GROUP BY species
)
SELECT
    species,
    n_years,
    ROUND((100.0 * (EXP(log_slope) - 1))::NUMERIC, 1)  AS annual_pct_rate,  -- compound %/yr
    ROUND(r2::NUMERIC, 3)                    AS trend_strength_r2,
    CASE
        -- require BOTH a meaningful slope AND a reasonably strong trend (R2)
        WHEN EXP(log_slope) - 1 <= -0.05 AND r2 >= 0.5 THEN 'DECLINING (clear)'
        WHEN EXP(log_slope) - 1 <= -0.02 AND r2 >= 0.5 THEN 'DECLINING (mild)'
        WHEN EXP(log_slope) - 1 >=  0.05 AND r2 >= 0.5 THEN 'GROWING (clear)'
        WHEN r2 < 0.5                                   THEN 'NO CLEAR TREND'
        ELSE 'STABLE'
    END AS classification
FROM fit
ORDER BY annual_pct_rate ASC;
