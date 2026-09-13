CREATE SCHEMA IF NOT EXISTS staging;

-- Purpose: cleaned, unioned gross-rent baseline by county/bedroom, combining
-- HUD FMR (real, bedroom-level) and Census ACS median gross rent (real,
-- county-level only -- ACS has no bedroom breakdown, so those rows carry
-- bedroom_count = NULL and exist for county-level comparison, not for
-- joining to leases).
-- Grain: (county_fips, bedroom_count, source).
DROP TABLE IF EXISTS staging.stg_rent_baseline;
CREATE TABLE staging.stg_rent_baseline AS
    WITH hud AS (
        SELECT
            -- Generates a consistent UUID based on the HUD grain
            md5(concat('hud_', county_fips, '_', bedroom_count::text, '_', fmr_year::text)) AS stg_rent_baseline_id,
            county_fips,
            county_name,
            bedroom_count,
            fmr_amount    AS gross_rent,
            fmr_year      AS data_year,
            source,
            as_of_date
        FROM raw.hud_fmr
    ),
    acs AS (
        SELECT
            -- Generates a consistent UUID based on the ACS grain (using 'all' for missing bedroom count)
            md5(concat('acs_', county_fips, '_all_', acs_year::text)) AS stg_rent_baseline_id,
            county_fips,
            county_name,
            NULL::SMALLINT AS bedroom_count,
            median_gross_rent AS gross_rent,
            acs_year      AS data_year,
            source,
            as_of_date
        FROM raw.acs_median_rent
    )
    SELECT * FROM hud
    UNION ALL
    SELECT * FROM acs;

-- Purpose: synthetic lease concessions joined to their real HUD FMR baseline
-- rent by (county_fips, bedroom_count), so downstream NER math has a real
-- gross_rent to work from. Only joins against the HUD_FMR_API rows in
-- stg_rent_baseline -- ACS rows have no bedroom_count and can't join at
-- lease grain.
-- Grain: one row per synthetic lease.
DROP TABLE IF EXISTS staging.stg_lease_terms;
CREATE TABLE staging.stg_lease_terms AS
    SELECT
        -- Generates a deterministic primary key for the staging table
        md5(concat('stg_lease_', l.lease_key)) AS stg_lease_term_id,
        l.lease_key,
        l.county_fips,
        b.county_name,
        l.bedroom_count,
        b.gross_rent,
        l.lease_term_months,
        l.free_rent_months,
        l.ti_allowance,
        l.is_synthetic
    FROM raw.synthetic_lease_concessions l
    JOIN staging.stg_rent_baseline b
        ON b.county_fips = l.county_fips
        AND b.bedroom_count = l.bedroom_count
        AND b.source = 'HUD_FMR_API';
