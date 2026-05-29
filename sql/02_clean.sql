-- ============================================================
-- 02_clean.sql  —  Raw staging → analysis table
-- ============================================================
-- Judgments live here. The most important ones:
--
-- 1. FILTER TO COMMERCIAL. The feed mixes commercial and recreational.
--    Recreational rows have NULL dollars and measure a different activity.
--
-- 2. WITHHELD ≠ ZERO. Confidential rows arrive as NULL pounds/dollars
--    OR as literal rows whose species NAME is "WITHHELD FOR CONFIDENTIALITY"
--    (NOAA's placeholder, e.g. 49 such rows for HAWAII 2011 alone). Both
--    forms are kept but flagged; neither becomes 0.
--
-- 3. AGGREGATE ROLLUPS are excluded from per-species analysis. NOAA
--    publishes many catch-all names: UNCLASSIFIED, ", UNC", SPP, OTHER,
--    and broad taxonomic buckets like "VERTEBRATES, JAWED" (50+ rows per
--    state-year). We flag any species name that is an aggregator.
--
-- 4. NO PK ON (species, state, year). Multiple rows per tuple exist
--    legitimately (different sub-sources). Analysis queries GROUP BY when
--    they need to.
-- ============================================================

TRUNCATE landings;

INSERT INTO landings (
    tsn, species, scientific_name, region, state, year,
    pounds, dollars, source, is_withheld, is_aggregate
)
SELECT
    tsn,
    ts_afs_name                      AS species,
    ts_scientific_name               AS scientific_name,
    region_name                      AS region,
    state_name                       AS state,
    year,
    NULLIF(pounds, '')::NUMERIC      AS pounds,
    NULLIF(dollars, '')::NUMERIC     AS dollars,
    source,
    (   pounds IS NULL OR pounds = ''
     OR dollars IS NULL OR dollars = ''
     OR ts_afs_name ILIKE 'WITHHELD%'
    ) AS is_withheld,
    (   ts_afs_name ILIKE '%UNCLASSIFIED%'
     OR ts_afs_name ILIKE '%, UNC%'
     OR ts_afs_name ILIKE '%SPP%'
     OR ts_afs_name ILIKE '%OTHER%'
     OR ts_afs_name ILIKE '%VERTEBRATES%'           -- "VERTEBRATES, JAWED" etc.
     OR ts_afs_name ILIKE 'FISHES%'                 -- broad finfish rollups
     OR ts_afs_name ILIKE 'SHELLFISHES%'
     OR ts_afs_name ILIKE '%, NS%'                  -- "not specified"
     OR ts_afs_name ILIKE '%, MIXED%'
     OR ts_afs_name LIKE '%**%'                     -- NOAA marks family/group aggregates with **
     OR ts_afs_name ILIKE 'WITHHELD%'
    ) AS is_aggregate
FROM landings_raw
WHERE year IS NOT NULL
  AND ts_afs_name IS NOT NULL
  AND collection = 'Commercial';   -- COMMERCIAL ONLY
