WITH net_effective_rent AS (
    SELECT 
        county_name,
        ROUND(AVG(gross_rent), 2) AS avg_gross_rent,
        ROUND(AVG(
                (gross_rent * lease_term_months - total_concession_dollars)
                / lease_term_months
            )
        ,2) AS avg_net_effective_rent,
        ROUND(AVG(
                100.0 * (
                    gross_rent - (
                        (gross_rent * lease_term_months - total_concession_dollars)
                        / lease_term_months
                    )
                ) / gross_rent
            )
        ,2) AS avg_ner_discount_pct
        FROM analytics.vw_net_effective_rent
        GROUP BY county_name
) 
SELECT * FROM net_effective_rent
ORDER BY avg_ner_discount_pct DESC, avg_net_effective_rent DESC;