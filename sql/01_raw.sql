-- Purpose: one row per Colorado county + bedroom count, from the HUD Fair Market Rents API. 
-- Grain: (county_fips, bedroom_count, fmr_year).
    CREATE TABLE IF NOT EXISTS raw.hud_fmr (
        hud_fmr_id      VARCHAR(36)  DEFAULT UUID_STRING()  PRIMARY KEY,
        county_fips     TEXT        NOT NULL,
        county_name     TEXT        NOT NULL,
        state_code      TEXT        NOT NULL,
        bedroom_count   SMALLINT    NOT NULL, -- 0 = studio
        fmr_amount      NUMERIC(10, 2) NOT NULL,
        fmr_year        SMALLINT    NOT NULL,
        source          TEXT        NOT NULL,
        as_of_date      DATE        NOT NULL DEFAULT CURRENT_DATE,
        CONSTRAINT unique_county_bedroom_year
            UNIQUE (county_fips, bedroom_count, fmr_year)

    );
-- Purpose: one row per Colorado county, from Census ACS 5-Year Table B25064 (median gross rent).
-- Grain: (county_fips, acs_year).
    CREATE TABLE IF NOT EXISTS raw.acs_median_rent (
        acs_median_rent_id  VARCHAR(36)  DEFAULT UUID_STRING()  PRIMARY KEY,
        county_fips         TEXT        NOT NULL,
        county_name         TEXT        NOT NULL,
        median_gross_rent   NUMERIC(10, 2) NOT NULL,
        acs_year            SMALLINT    NOT NULL,
        source              TEXT        NOT NULL,
        as_of_date          DATE        NOT NULL DEFAULT CURRENT_DATE,
        CONSTRAINT unique_county_acs_year
            UNIQUE (county_fips, acs_year)
    );
-- Purpose: synthetic lease-level concession data. No public dataset publishes real tenant concessions, so this is generated (seeded/reproducible) rather than sourced. is_synthetic must stay TRUE here
-- never blend real and synthetic rows in the same table without the flag.
-- Grain: one row per synthetic lease. lease_key is the deterministic natural
-- key transform.py generates (county_fips-bedroom_count-index); it's what
-- etl/load.py upserts on so reruns with the same seed don't duplicate rows.
    CREATE TABLE IF NOT EXISTS raw.synthetic_lease_concessions (
        synthetic_lease_concessions_id  VARCHAR(36)  DEFAULT UUID_STRING()  PRIMARY KEY,
        lease_key                       TEXT        NOT NULL UNIQUE,
        county_fips                     TEXT        NOT NULL,
        bedroom_count                   SMALLINT    NOT NULL,
        lease_term_months               SMALLINT    NOT NULL,
        free_rent_months                NUMERIC(4, 2) NOT NULL DEFAULT 0,
        ti_allowance                    NUMERIC(10, 2) NOT NULL DEFAULT 0,
        is_synthetic                    BOOLEAN     NOT NULL DEFAULT TRUE,
        created_at                      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
    );