"""
etl/transform.py

Cleans the raw HUD/Census JSON pulled by etl/extract.py into the shapes
raw.hud_fmr_co and raw.acs_median_rent_co expect, and generates the
synthetic lease concessions table.

Real data (HUD, Census) is never altered beyond type/shape cleanup. The
concessions data has no public source, so it's generated here with a
seeded RNG: same seed -> same rows every run, so reruns of the pipeline
don't produce different "real" numbers to reason about, and a reviewer
can regenerate the exact same dataset from this file alone.

Run directly for a standalone transform step (reads etl/data/raw/,
writes etl/data/processed/):
    python etl/transform.py
Or import transform_all() from etl/run_pipeline.py.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DATA_DIR = Path(__file__).parent / "data" / "raw"
PROCESSED_DATA_DIR = Path(__file__).parent / "data" / "processed"
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Fixed seed for the synthetic concessions generator — see
# generate_synthetic_lease_concessions() below for why this matters.
SYNTHETIC_SEED = 42

# Lease terms, weighted toward the common 12/24-month residential terms.
LEASE_TERM_MONTHS_CHOICES = [12, 18, 24, 36, 60]
LEASE_TERM_MONTHS_WEIGHTS = [40, 15, 30, 10, 5]

# Free-rent months offered as a concession. Weighted so a large share of
# leases have none at all (mirrors real markets, where concessions are the
# exception, not the rule) this is also what gives the demo a lease with
# ner_discount_pct = 0 to show alongside the discounted ones.
FREE_RENT_MONTHS_CHOICES = [0, 0.5, 1, 1.5, 2, 3]
FREE_RENT_MONTHS_WEIGHTS = [35, 10, 25, 10, 15, 5]

# TI (tenant improvement) allowance in flat dollars. Most residential-style
# leases get none; a minority get a small move-in/build-out credit.
TI_ALLOWANCE_CHOICES = [0, 250, 500, 1000, 1500]
TI_ALLOWANCE_WEIGHTS = [55, 15, 15, 10, 5]

# How many synthetic leases to generate per (county, bedroom_count) combo
# found in the real rent baseline.
LEASES_PER_BASELINE_ROW_CHOICES = [1, 2, 3]
LEASES_PER_BASELINE_ROW_WEIGHTS = [50, 35, 15]


# ---------------------------------------------------------------------------
# HUD Fair Market Rents
# ---------------------------------------------------------------------------

def transform_hud_fmr(raw_rows: list[dict]) -> list[dict]:
    """Cleans extract.py's HUD output into raw.hud_fmr_co's shape.

    extract_hud_fmr_colorado() already flattens to one dict per
    (county, bedroom_count) with the right keys, so this is mostly
    validation + dropping rows extract.py couldn't fully populate
    (e.g. a missing fmr_year).
    """
    today = date.today().isoformat()
    rows = []
    for row in raw_rows:
        if row.get("fmr_year") is None:
            log.warning("Dropping HUD row with no fmr_year: %s", row)
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
    log.info("Transformed %d/%d HUD FMR rows", len(rows), len(raw_rows))
    return rows


# ---------------------------------------------------------------------------
# Census ACS 5-Year (Table B25064)
# ---------------------------------------------------------------------------

def transform_acs_median_rent(raw_rows: list[dict]) -> list[dict]:
    """Cleans extract.py's ACS output into raw.acs_median_rent_co's shape."""
    today = date.today().isoformat()
    rows = []
    for row in raw_rows:
        rows.append(
            {
                "county_fips": row["county_fips"],
                "county_name": row["county_name"],
                "median_gross_rent": round(float(row["median_gross_rent"]), 2),
                "acs_year": int(row["acs_year"]),
                "source": row.get("source", "CENSUS_ACS5_B25064"),
                "as_of_date": today,
            }
        )
    log.info("Transformed %d/%d ACS median rent rows", len(rows), len(raw_rows))
    return rows


# ---------------------------------------------------------------------------
# Synthetic lease concessions
# ---------------------------------------------------------------------------

def generate_synthetic_lease_concessions(
    hud_fmr_rows: list[dict], seed: int = SYNTHETIC_SEED
) -> list[dict]:
    """Generates synthetic lease-level concession rows, one baseline row at
    a time, so every synthetic lease can join back to a real gross rent by
    (county_fips, bedroom_count) — that join is staging.stg_lease_terms.

    Method (deterministic, documented, no hand-typed rows):
      - Seed a dedicated random.Random(seed) instance (default 42).
      - For every unique (county_fips, bedroom_count) pair in the real HUD
        baseline, draw 1-3 synthetic leases.
      - Each lease independently draws lease_term_months, free_rent_months,
        and ti_allowance from the weighted distributions above.
      - Iteration order is the sorted baseline keys, so the same input
        always produces the same output rows in the same order.

    Because the seed and iteration order are both fixed, rerunning this
    against the same HUD baseline reproduces byte-identical output — that's
    what "seeded/reproducible" means here, not that the values are hidden
    real data.
    """
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
                    # Deterministic natural key (not a DB identity) so a
                    # rerun with the same seed can MERGE instead of
                    # duplicating rows.
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

    log.info(
        "Generated %d synthetic lease concession rows across %d baseline combos (seed=%d)",
        len(rows),
        len(baseline_keys),
        seed,
    )
    return rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _read_raw_json(filename: str) -> list[dict]:
    path = RAW_DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `python etl/extract.py` first to pull real data."
        )
    return json.loads(path.read_text())


def transform_all() -> dict[str, Path]:
    """Runs all transforms and writes cleaned JSON files. Returns output paths."""
    hud_raw = _read_raw_json("hud_fmr_co_raw.json")
    hud_rows = transform_hud_fmr(hud_raw)
    hud_path = PROCESSED_DATA_DIR / "hud_fmr_co.json"
    hud_path.write_text(json.dumps(hud_rows, indent=2))
    log.info("Wrote %s (%d rows)", hud_path, len(hud_rows))

    acs_raw = _read_raw_json("acs_median_rent_co_raw.json")
    acs_rows = transform_acs_median_rent(acs_raw)
    acs_path = PROCESSED_DATA_DIR / "acs_median_rent_co.json"
    acs_path.write_text(json.dumps(acs_rows, indent=2))
    log.info("Wrote %s (%d rows)", acs_path, len(acs_rows))

    synthetic_rows = generate_synthetic_lease_concessions(hud_rows)
    synthetic_path = PROCESSED_DATA_DIR / "synthetic_lease_concessions.json"
    synthetic_path.write_text(json.dumps(synthetic_rows, indent=2))
    log.info("Wrote %s (%d rows)", synthetic_path, len(synthetic_rows))

    return {
        "hud_fmr": hud_path,
        "acs_median_rent": acs_path,
        "synthetic_lease_concessions": synthetic_path,
    }


if __name__ == "__main__":
    transform_all()
