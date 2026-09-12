"""
etl/transform.py

Cleans the raw HUD/Census JSON into the shapes raw.hud_fmr and
raw.acs_median_rent, and generates the synthetic lease
concessions table (no public source for that data, so it's simulated).
"""

from __future__ import annotations

import json
import random
from datetime import date
from pathlib import Path

RAW_DATA_DIR = Path(__file__).parent / "data" / "raw"
PROCESSED_DATA_DIR = Path(__file__).parent / "data" / "processed"
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Fixed seed so reruns produce byte-identical synthetic rows -- no
# hand-typed data, but also no drift between runs.
SYNTHETIC_SEED = 42

LEASE_TERM_MONTHS_CHOICES = [12, 18, 24, 36, 60]
LEASE_TERM_MONTHS_WEIGHTS = [40, 15, 30, 10, 5]

# Weighted so most leases have no free rent, mirroring real markets where
# concessions are the exception.
FREE_RENT_MONTHS_CHOICES = [0, 0.5, 1, 1.5, 2, 3]
FREE_RENT_MONTHS_WEIGHTS = [35, 10, 25, 10, 15, 5]

TI_ALLOWANCE_CHOICES = [0, 250, 500, 1000, 1500]
TI_ALLOWANCE_WEIGHTS = [55, 15, 15, 10, 5]

LEASES_PER_BASELINE_ROW_CHOICES = [1, 2, 3]
LEASES_PER_BASELINE_ROW_WEIGHTS = [50, 35, 15]


def transform_hud_fmr(raw_rows: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    rows = []
    for row in raw_rows:
        if row.get("fmr_year") is None:
            continue
        rows.append(
            {
                "county_fips": row["county_fips"],
                "county_name": row["county_name"],
                "state_code": row.get("state_code", "CO"),
                "bedroom_count": int(row["bedroom_count"]),
                "fmr_amount": round(float(row["fmr_amount"]), 2),
                "fmr_year": int(row["fmr_year"]),
                "source": row.get("source", "HUD_FMR_API"),
                "as_of_date": today,
            }
        )
    return rows


def transform_acs_median_rent(raw_rows: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    return [
        {
            "county_fips": row["county_fips"],
            "county_name": row["county_name"],
            "median_gross_rent": round(float(row["median_gross_rent"]), 2),
            "acs_year": int(row["acs_year"]),
            "source": row.get("source", "CENSUS_ACS5_B25064"),
            "as_of_date": today,
        }
        for row in raw_rows
    ]


def generate_synthetic_lease_concessions(
    hud_fmr_rows: list[dict], seed: int = SYNTHETIC_SEED
) -> list[dict]:
    """One synthetic lease at a time, per (county_fips, bedroom_count) in
    the real HUD baseline, so every lease can join back to a real rent."""
    rng = random.Random(seed)
    baseline_keys = sorted(
        {(row["county_fips"], row["county_name"], row["bedroom_count"]) for row in hud_fmr_rows}
    )

    rows = []
    for county_fips, county_name, bedroom_count in baseline_keys:
        num_leases = rng.choices(
            LEASES_PER_BASELINE_ROW_CHOICES, weights=LEASES_PER_BASELINE_ROW_WEIGHTS
        )[0]
        for i in range(num_leases):
            lease_term_months = rng.choices(
                LEASE_TERM_MONTHS_CHOICES, weights=LEASE_TERM_MONTHS_WEIGHTS
            )[0]
            free_rent_months = rng.choices(
                FREE_RENT_MONTHS_CHOICES, weights=FREE_RENT_MONTHS_WEIGHTS
            )[0]
            ti_allowance = rng.choices(TI_ALLOWANCE_CHOICES, weights=TI_ALLOWANCE_WEIGHTS)[0]

            rows.append(
                {
                    # Deterministic natural key so a rerun with the same
                    # seed MERGEs instead of duplicating rows.
                    "lease_key": f"{county_fips}-{bedroom_count}-{i}",
                    "county_fips": county_fips,
                    "county_name": county_name,
                    "bedroom_count": bedroom_count,
                    "lease_term_months": lease_term_months,
                    "free_rent_months": free_rent_months,
                    "ti_allowance": float(ti_allowance),
                    "is_synthetic": True,
                }
            )

    return rows


def _read_raw_json(filename: str) -> list[dict]:
    return json.loads((RAW_DATA_DIR / filename).read_text())


def transform_all() -> dict[str, Path]:
    hud_rows = transform_hud_fmr(_read_raw_json("hud_fmr_raw.json"))
    hud_path = PROCESSED_DATA_DIR / "hud_fmr.json"
    hud_path.write_text(json.dumps(hud_rows, indent=2))

    acs_rows = transform_acs_median_rent(_read_raw_json("acs_median_rent_raw.json"))
    acs_path = PROCESSED_DATA_DIR / "acs_median_rent.json"
    acs_path.write_text(json.dumps(acs_rows, indent=2))

    synthetic_rows = generate_synthetic_lease_concessions(hud_rows)
    synthetic_path = PROCESSED_DATA_DIR / "synthetic_lease_concessions.json"
    synthetic_path.write_text(json.dumps(synthetic_rows, indent=2))

    return {
        "hud_fmr": hud_path,
        "acs_median_rent": acs_path,
        "synthetic_lease_concessions": synthetic_path,
    }


if __name__ == "__main__":
    transform_all()