CREATE SCHEMA IF NOT EXISTS analytics;
CREATE OR REPLACE VIEW analytics.vw_net_effective_rent AS
SELECT
    lease_key,
    county_fips,
    county_name,
    bedroom_count,
    gross_rent,
    lease_term_months,
    free_rent_months,
    ti_allowance,
    ROUND(free_rent_months * gross_rent + ti_allowance, 2) AS total_concession_dollars,
    is_synthetic
FROM staging.stg_lease_terms;