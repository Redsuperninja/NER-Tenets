WITH net_effective_rent AS (
    SELECT 
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
        ) AS ner_discount_pct
        FROM analytics.vw_net_effective_rent
) 
SELECT * FROM net_effective_rent
WHERE ner_discount_pct BETWEEN 0 AND 8.5
ORDER BY ner_discount_pct ASC, net_effective_rent DESC;