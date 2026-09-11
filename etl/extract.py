"""
etl/extract.py

Pulls real public data for Colorado counties from two APIs and writes the
raw JSON responses to etl/data/raw/. No manual downloads — everything here
is scriptable and rerunnable.

Sources:
  - HUD Fair Market Rents API   https://www.huduser.gov/portal/dataset/fmr-api.html
  - Census ACS 5-Year API       https://www.census.gov/data/developers/data-sets/acs-5year.html

Run directly for a standalone extract step:
    python etl/extract.py
Or import extract_all() from etl/run_pipeline.py.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RAW_DATA_DIR = Path(__file__).parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

HUD_API_TOKEN = os.environ.get("HUD_API_TOKEN")
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")

HUD_BASE_URL = "https://www.huduser.gov/hudapi/public"
CENSUS_ACS_YEAR = "2023"  # most recent 5-Year ACS release at time of writing
CENSUS_BASE_URL = f"https://api.census.gov/data/{CENSUS_ACS_YEAR}/acs/acs5"
COLORADO_STATE_ABBR = "CO"
COLORADO_STATE_FIPS = "08"

# HUD's own year param — the FMR "fiscal year" to request. Falls back to
# HUD's default (current FY) if left as None.
HUD_FMR_YEAR = None

# Maps HUD's basicdata keys to a plain bedroom_count integer.
HUD_BEDROOM_KEY_MAP = {
    "Efficiency": 0,
    "One-Bedroom": 1,
    "Two-Bedroom": 2,
    "Three-Bedroom": 3,
    "Four-Bedroom": 4,
}

REQUEST_TIMEOUT_SECONDS = 15
REQUEST_PAUSE_SECONDS = 0.5 #Pause between requests to avoid rate-limiting


def _require_env(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


# ---------------------------------------------------------------------------
# HUD Fair Market Rents
# ---------------------------------------------------------------------------

def _hud_headers() -> dict:
    token = _require_env("HUD_API_TOKEN", HUD_API_TOKEN)
    return {"Authorization": f"Bearer {token}"}


def get_colorado_counties_from_hud() -> list[dict]:
    """Returns [{fips_code, county_name}, ...] for every CO county HUD knows about.

    fips_code is HUD's 10-digit entity id (5-digit county FIPS + '99999').
    """
    url = f"{HUD_BASE_URL}/fmr/listCounties/{COLORADO_STATE_ABBR}"
    log.info("Fetching Colorado county list from HUD: %s", url)
    resp = requests.get(url, headers=_hud_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    # Unlike the per-county fmr/data/{fips} endpoint, listCounties returns a bare JSON array — not wrapped in {"data": [...]}.
    counties = resp.json()
    log.info("HUD returned %d Colorado counties", len(counties))
    return counties


HUD_MAX_RETRIES = 3
HUD_RETRY_BACKOFF_SECONDS = 2.0


def get_hud_fmr_for_county(entity_fips_code: str) -> dict:
    """Returns the raw HUD response for one county entity id.

    Retries with backoff on 429 — the free HUD tier rate-limits, and a
    64-county loop can trip it near the end even with REQUEST_PAUSE_SECONDS
    between calls.
    """
    url = f"{HUD_BASE_URL}/fmr/data/{entity_fips_code}"
    params = {"year": HUD_FMR_YEAR} if HUD_FMR_YEAR else {}

    for attempt in range(1, HUD_MAX_RETRIES + 1):
        resp = requests.get(
            url, headers=_hud_headers(), params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if resp.status_code == 429 and attempt < HUD_MAX_RETRIES:
            wait = HUD_RETRY_BACKOFF_SECONDS * attempt
            log.warning("Rate limited on %s, retrying in %.1fs", entity_fips_code, wait)
            time.sleep(wait)
            continue
        break

    resp.raise_for_status()
    return resp.json()["data"]


def extract_hud_fmr_colorado() -> list[dict]:
    """Pulls FMR data for every Colorado county and flattens it to one row
    per (county, bedroom_count)."""
    counties = get_colorado_counties_from_hud()
    rows: list[dict] = []

    for county in counties:
        entity_id = county["fips_code"]
        county_fips_5digit = entity_id[:5]

        try:
            fmr = get_hud_fmr_for_county(entity_id)
        except requests.HTTPError as exc:
            log.warning("Skipping %s (%s): %s", county["county_name"], entity_id, exc)
            continue

        basicdata = fmr.get("basicdata", {})

        # Small Area FMR counties (e.g. El Paso, Pueblo) return basicdata as
        # a list of per-ZIP rows instead of one county-level dict, and put
        # `year` on the outer `fmr` object instead of inside basicdata. Use
        # the "MSA level" row as the county-wide rate in that case.
        if isinstance(basicdata, list):
            fmr_year = int(fmr["year"]) if fmr.get("year") else None
            msa_row = next((row for row in basicdata if row.get("zip_code") == "MSA level"), None)
            if msa_row is None:
                log.warning(
                    "No MSA-level row for %s (%s); skipping", county["county_name"], entity_id
                )
                continue
            basicdata = msa_row
        else:
            fmr_year = int(basicdata["year"]) if basicdata.get("year") else None

        for hud_key, bedroom_count in HUD_BEDROOM_KEY_MAP.items():
            if hud_key not in basicdata:
                continue
            rows.append(
                {
                    "county_fips": county_fips_5digit,
                    "county_name": county["county_name"],
                    "state_code": COLORADO_STATE_ABBR,
                    "bedroom_count": bedroom_count,
                    "fmr_amount": float(basicdata[hud_key]),
                    "fmr_year": fmr_year,
                    "source": "HUD_FMR_API",
                }
            )

        time.sleep(REQUEST_PAUSE_SECONDS)

    log.info("Extracted %d HUD FMR rows for Colorado", len(rows))
    return rows


# ---------------------------------------------------------------------------
# Census ACS 5-Year (Table B25064 — median gross rent)
# ---------------------------------------------------------------------------

def extract_acs_median_rent_colorado() -> list[dict]:
    """Pulls median gross rent (B25064_001E) for every Colorado county."""
    api_key = _require_env("CENSUS_API_KEY", CENSUS_API_KEY)

    params = {
        "get": "B25064_001E,NAME",
        "for": "county:*",
        "in": f"state:{COLORADO_STATE_FIPS}",
        "key": api_key,
    }
    log.info("Fetching Colorado ACS median gross rent from Census API")
    resp = requests.get(CENSUS_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()

    raw_rows = resp.json()
    header, *data_rows = raw_rows  # first row is the column header

    rows: list[dict] = []
    for row in data_rows:
        record = dict(zip(header, row))
        median_rent = record.get("B25064_001E")
        # Census uses negative sentinel codes (e.g. -666666666) for
        # suppressed/unavailable estimates — skip those.
        if median_rent is None or float(median_rent) < 0:
            continue

        county_fips = f"{record['state']}{record['county']}"
        county_name = record["NAME"].split(",")[0]  # "Denver County, Colorado" -> "Denver County"

        rows.append(
            {
                "county_fips": county_fips,
                "county_name": county_name,
                "median_gross_rent": float(median_rent),
                "acs_year": int(CENSUS_ACS_YEAR),
                "source": "CENSUS_ACS5_B25064",
            }
        )

    log.info("Extracted %d ACS median rent rows for Colorado", len(rows))
    return rows


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def extract_all() -> dict[str, Path]:
    """Runs both extracts and writes raw JSON files. Returns the output paths."""
    hud_rows = extract_hud_fmr_colorado()
    hud_path = RAW_DATA_DIR / "hud_fmr_co_raw.json"
    hud_path.write_text(json.dumps(hud_rows, indent=2))
    log.info("Wrote %s (%d rows)", hud_path, len(hud_rows))

    acs_rows = extract_acs_median_rent_colorado()
    acs_path = RAW_DATA_DIR / "acs_median_rent_co_raw.json"
    acs_path.write_text(json.dumps(acs_rows, indent=2))
    log.info("Wrote %s (%d rows)", acs_path, len(acs_rows))

    return {"hud_fmr": hud_path, "acs_median_rent": acs_path}


if __name__ == "__main__":
    extract_all()