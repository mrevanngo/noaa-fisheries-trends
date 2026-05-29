-- ============================================================
-- 01_schema.sql  —  PostgreSQL schema for NOAA FOSS landings
-- ============================================================
-- Columns match the live NOAA FOSS REST feed
-- (apps-st.fisheries.noaa.gov/ods/foss/landings/):
--   tsn, ts_afs_name, ts_scientific_name, region_name, state_name,
--   year, pounds, dollars, tot_count, source, collection
--
-- Design decisions (interview talking points):
--
-- * Load into a loosely-typed RAW staging table first, because the feed
--   contains NULLs (dollars is null for recreational rows; pounds/dollars
--   can be withheld) AND the same logical species-state-year can appear
--   multiple times under different sub-sources. Raw-then-transform keeps
--   ingest robust and cleaning auditable.
--
-- * The feed mixes COMMERCIAL and RECREATIONAL landings. This project
--   studies commercial fisheries, so the clean step filters accordingly.
--
-- * "state_name" is the LANDING/SALE location, NOT the catch location.
-- ============================================================

DROP TABLE IF EXISTS landings_raw CASCADE;

CREATE TABLE landings_raw (
    tsn                 TEXT,
    ts_afs_name         TEXT,
    ts_scientific_name  TEXT,
    region_name         TEXT,
    state_name          TEXT,
    year                INTEGER,
    pounds              TEXT,
    dollars             TEXT,
    tot_count           TEXT,
    source              TEXT,
    collection          TEXT
);

-- Cleaned, analysis-ready table.
--
-- NO primary key on (species, state, year) — the real feed contains
-- multiple rows per that tuple (different sources, repeated placeholders
-- like 'WITHHELD FOR CONFIDENTIALITY'). We use a synthetic id and let the
-- analysis queries do their own GROUP BY when they want one row per tuple.
DROP TABLE IF EXISTS landings CASCADE;

CREATE TABLE landings (
    id              BIGSERIAL PRIMARY KEY,
    tsn             TEXT,
    species         TEXT    NOT NULL,
    scientific_name TEXT,
    region          TEXT,
    state           TEXT    NOT NULL,
    year            INTEGER NOT NULL,
    pounds          NUMERIC,        -- NULL when withheld (never 0)
    dollars         NUMERIC,        -- NULL when withheld (never 0)
    source          TEXT,
    is_withheld     BOOLEAN NOT NULL DEFAULT FALSE,
    is_aggregate    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_landings_species ON landings (species);
CREATE INDEX idx_landings_year    ON landings (year);
CREATE INDEX idx_landings_state   ON landings (state);
CREATE INDEX idx_landings_region  ON landings (region);
CREATE INDEX idx_landings_clean   ON landings (species, state, year)
    WHERE NOT is_withheld AND NOT is_aggregate;
