"""
etl/extract.py

Pulls HUD Fair Market Rent and Census ACS median rent data for Colorado
counties and writes the raw JSON to etl/data/raw/.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

RAW_DATA_DIR = Path(__file__).parent / "data" / "raw"
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

HUD_BASE_URL = "https://www.huduser.gov/hudapi/public"
CENSUS_ACS_YEAR = "2023"
CENSUS_BASE_URL = f"https://api.census.gov/data/{CENSUS_ACS_YEAR}/acs/acs5"
COLORADO_STATE_ABBR = "CO"
COLORADO_STATE_FIPS = "08"

# Maps HUD's basicdata keys to a plain bedroom_count integer.
HUD_BEDROOM_KEY_MAP = {
    "Efficiency": 0,
    "One-Bedroom": 1,
    "Two-Bedroom": 2,
    "Three-Bedroom": 3,
    "Four-Bedroom": 4,
}

REQUEST_TIMEOUT_SECONDS = 15
REQUEST_PAUSE_SECONDS = 0.5  # avoid tripping HUD's rate limit


def _hud_headers() -> dict:
    token = os.environ["HUD_API_TOKEN"]
    return {"Authorization": f"Bearer {token}"}


def get_colorado_counties_from_hud() -> list[dict]:
    """Returns [{fips_code, county_name}, ...] for every CO county."""
    url = f"{HUD_BASE_URL}/fmr/listCounties/{COLORADO_STATE_ABBR}"
    resp = requests.get(url, headers=_hud_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def get_hud_fmr_for_county(entity_fips_code: str) -> dict:
    url = f"{HUD_BASE_URL}/fmr/data/{entity_fips_code}"
    resp = requests.get(url, headers=_hud_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()["data"]


def extract_hud_fmr_colorado() -> list[dict]:
    """Pulls FMR data for every Colorado county, flattened to one row per
    (county, bedroom_count)."""
    counties = get_colorado_counties_from_hud()
    rows: list[dict] = []

    for county in counties:
        entity_id = county["fips_code"]
        county_fips_5digit = entity_id[:5]
        fmr = get_hud_fmr_for_county(entity_id)
        basicdata = fmr.get("basicdata", {})

        # Small Area FMR counties (e.g. El Paso, Pueblo) return basicdata as
        # a list of per-ZIP rows instead of one county-level dict. Use the
        # "MSA level" row as the county-wide rate in that case.
        if isinstance(basicdata, list):
            fmr_year = int(fmr["year"]) if fmr.get("year") else None
            basicdata = next((r for r in basicdata if r.get("zip_code") == "MSA level"), {})
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

    return rows


def extract_acs_median_rent_colorado() -> list[dict]:
    """Pulls median gross rent (B25064_001E) for every Colorado county."""
    params = {
        "get": "B25064_001E,NAME",
        "for": "county:*",
        "in": f"state:{COLORADO_STATE_FIPS}",
        "key": os.environ["CENSUS_API_KEY"],
    }
    resp = requests.get(CENSUS_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()

    header, *data_rows = resp.json()  # first row is the column header
    rows: list[dict] = []
    for row in data_rows:
        record = dict(zip(header, row))
        median_rent = record.get("B25064_001E")
        # Census uses negative sentinel codes (e.g. -666666666) for
        # suppressed/unavailable estimates -- skip those.
        if median_rent is None or float(median_rent) < 0:
            continue

        rows.append(
            {
                "county_fips": f"{record['state']}{record['county']}",
                "county_name": record["NAME"].split(",")[0],
                "median_gross_rent": float(median_rent),
                "acs_year": int(CENSUS_ACS_YEAR),
                "source": "CENSUS_ACS5_B25064",
            }
        )

    return rows


def extract_all() -> dict[str, Path]:
    hud_path = RAW_DATA_DIR / "hud_fmr_raw.json"
    hud_path.write_text(json.dumps(extract_hud_fmr_colorado(), indent=2))

    acs_path = RAW_DATA_DIR / "acs_median_rent_raw.json"
    acs_path.write_text(json.dumps(extract_acs_median_rent_colorado(), indent=2))

    return {"hud_fmr": hud_path, "acs_median_rent": acs_path}


if __name__ == "__main__":
    extract_all()