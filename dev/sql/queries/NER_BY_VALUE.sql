SELECT
    county_name,
    gross_rent,
    lease_term_months,
    free_rent_months,
    ti_allowance,
    total_concession_dollars,
    ROUND(
        (gross_rent * lease_term_months - total_concession_dollars)
        / lease_term_months,
        2
    ) AS net_effective_rent,
    ROUND(
        100.0 * (
            gross_rent - (
                (gross_rent * lease_term_months - total_concession_dollars)
                / lease_term_months
            )
        ) / gross_rent,
        2
    ) AS ner_discount_pct,
    is_synthetic
FROM analytics.vw_net_effective_rent
ORDER BY net_effective_rent DESC;