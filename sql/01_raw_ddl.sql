-- Snowflake port of dev/sql/raw.sql -- see that file for the Postgres
-- prototype this was validated against. Differences: NUMBER instead of
-- NUMERIC, IDENTITY instead of SERIAL; everything else is unchanged.

USE WAREHOUSE NER_DEMO_WH;
USE DATABASE NER_DEMO;

-- Purpose: one row per Colorado county + bedroom count, from the HUD Fair Market Rents API. 
-- Grain: (county_fips, bedroom_count, fmr_year).
CREATE TABLE IF NOT EXISTS raw.hud_fmr_co (
    hud_fmr_id      GUID      PRIMARY KEY,
    county_fips     TEXT        NOT NULL,
    county_name     TEXT        NOT NULL,
    state_code      TEXT        NOT NULL,
    bedroom_count   SMALLINT    NOT NULL, -- 0 = studio
    fmr_amount      NUMBER(10, 2) NOT NULL,
    fmr_year        SMALLINT    NOT NULL,
    source          TEXT        NOT NULL,
    as_of_date      DATE        NOT NULL DEFAULT CURRENT_DATE(),
    UNIQUE KEY (county_fips, bedroom_count, fmr_year)
);

-- Purpose: one row per Colorado county, from Census ACS 5-Year Table B25064 (median gross rent).
-- Grain: (county_fips, acs_year).
CREATE TABLE IF NOT EXISTS raw.acs_median_rent_co (
    acs_median_rent_id  GUID PRIMARY KEY,
    county_fips         TEXT        NOT NULL,
    county_name         TEXT        NOT NULL,
    median_gross_rent   NUMBER(10, 2) NOT NULL,
    acs_year            SMALLINT    NOT NULL,
    source              TEXT        NOT NULL,
    as_of_date          DATE        NOT NULL DEFAULT CURRENT_DATE(),
    UNIQUE KEY (county_fips, acs_year)
);

-- Purpose: synthetic lease-level concession data. No public dataset publishes real tenant concessions, so this is generated (seeded/reproducible) rather than sourced. is_synthetic must stay TRUE here
-- never blend real and synthetic rows in the same table without the flag.
-- Grain: one row per synthetic lease. lease_key is the deterministic natural
-- key transform.py generates (county_fips-bedroom_count-index); it's what
-- etl/load.py upserts on so reruns with the same seed don't duplicate rows.
CREATE TABLE IF NOT EXISTS raw.synthetic_lease_concessions (
    lease_id            INTEGER     IDENTITY PRIMARY KEY,
    lease_key           TEXT        NOT NULL UNIQUE,
    county_fips         TEXT        NOT NULL,
    bedroom_count       SMALLINT    NOT NULL,
    lease_term_months   SMALLINT    NOT NULL,
    free_rent_months    NUMBER(4, 2) NOT NULL DEFAULT 0,
    ti_allowance        NUMBER(10, 2) NOT NULL DEFAULT 0,
    is_synthetic        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);
