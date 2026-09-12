"""
etl/load.py

Loads the transformed JSON in etl/data/processed/ into raw.* tables.
Supports two targets so the load logic can be proven cheaply before it
touches real Snowflake credits:
  - "dev"       -> the disposable Postgres sandbox (dev/docker-compose.dev.yml,
                   schema from dev/sql/raw.sql)
  - "snowflake" -> the real Snowflake raw schema (sql/01_raw_ddl.sql)

Both paths upsert on the same natural keys so reruns never duplicate rows:
  - raw.hud_fmr                   : (county_fips, bedroom_count, fmr_year)
  - raw.acs_median_rent           : (county_fips, acs_year)
  - raw.synthetic_lease_concessions : (lease_key) -- see transform.py

Run directly:
    python etl/load.py --target dev
    python etl/load.py --target snowflake
Or import load_all() from etl/run_pipeline.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROCESSED_DATA_DIR = Path(__file__).parent / "data" / "processed"

# Natural keys used for idempotent upserts/MERGEs, one per raw table.
HUD_FMR_KEY = ("county_fips", "bedroom_count", "fmr_year")
ACS_MEDIAN_RENT_KEY = ("county_fips", "acs_year")
SYNTHETIC_LEASE_KEY = ("lease_key",)

HUD_FMR_COLUMNS = [
    "county_fips", "county_name", "state_code", "bedroom_count",
    "fmr_amount", "fmr_year", "source", "as_of_date",
]
ACS_MEDIAN_RENT_COLUMNS = [
    "county_fips", "county_name", "median_gross_rent", "acs_year", "source", "as_of_date",
]
# transform.py also carries county_name for readability, but it's not a
# column on raw.synthetic_lease_concessions -- staging joins back to
# stg_rent_baseline for that, so it's dropped here rather than stored twice.
SYNTHETIC_LEASE_COLUMNS = [
    "lease_key", "county_fips", "bedroom_count", "lease_term_months",
    "free_rent_months", "ti_allowance", "is_synthetic",
]


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def _read_processed(filename: str) -> list[dict]:
    path = PROCESSED_DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `python etl/transform.py` first.")
    return json.loads(path.read_text())


def _rows_for_columns(rows: list[dict], columns: list[str]) -> list[tuple]:
    return [tuple(row[col] for col in columns) for row in rows]


# ---------------------------------------------------------------------------
# Dev sandbox (Postgres)
# ---------------------------------------------------------------------------

def _postgres_connect():
    import psycopg2

    # Matches the throwaway credentials hardcoded in
    # dev/docker-compose.dev.yml -- local-only, fine to default here.
    return psycopg2.connect(
        host=os.environ.get("DEV_DB_HOST", "localhost"),
        port=os.environ.get("DEV_DB_PORT", "5432"),
        dbname=os.environ.get("DEV_DB_NAME", "ner_db"),
        user=os.environ.get("DEV_DB_USER", "ner_user"),
        password=os.environ.get("DEV_DB_PASSWORD", "ner_password"),
    )


def _postgres_upsert(cur, table: str, columns: list[str], key: tuple[str, ...], rows: list[tuple]) -> None:
    if not rows:
        log.info("No rows to load into %s, skipping", table)
        return

    update_cols = [c for c in columns if c not in key]
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(['%s'] * len(columns))}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    )
    cur.executemany(sql, rows)
    log.info("Upserted %d rows into %s (dev Postgres)", len(rows), table)


def load_to_postgres() -> None:
    hud_rows = _read_processed("hud_fmr.json")
    acs_rows = _read_processed("acs_median_rent.json")
    lease_rows = _read_processed("synthetic_lease_concessions.json")

    conn = _postgres_connect()
    try:
        with conn, conn.cursor() as cur:
            _postgres_upsert(cur, "raw.hud_fmr", HUD_FMR_COLUMNS, HUD_FMR_KEY,
                              _rows_for_columns(hud_rows, HUD_FMR_COLUMNS))
            _postgres_upsert(cur, "raw.acs_median_rent", ACS_MEDIAN_RENT_COLUMNS, ACS_MEDIAN_RENT_KEY,
                              _rows_for_columns(acs_rows, ACS_MEDIAN_RENT_COLUMNS))
            _postgres_upsert(cur, "raw.synthetic_lease_concessions", SYNTHETIC_LEASE_COLUMNS, SYNTHETIC_LEASE_KEY,
                              _rows_for_columns(lease_rows, SYNTHETIC_LEASE_COLUMNS))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Snowflake
# ---------------------------------------------------------------------------

def _snowflake_connect():
    import snowflake.connector

    return snowflake.connector.connect(
        account=_require_env("SNOWFLAKE_ACCOUNT"),
        user=_require_env("SNOWFLAKE_USER"),
        password=_require_env("SNOWFLAKE_PASSWORD"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "NER_DEMO_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "NER_DEMO"),
        role=os.environ.get("SNOWFLAKE_ROLE") or None,
        schema="RAW",
    )


def _snowflake_merge(cur, table: str, columns: list[str], key: tuple[str, ...], rows: list[tuple]) -> None:
    if not rows:
        log.info("No rows to load into %s, skipping", table)
        return

    # Stage rows in a session-scoped temp table, then MERGE from it -- lets
    # Snowflake upsert on the natural key in one statement instead of a
    # round trip per row.
    stage_table = f"{table.split('.')[-1]}_stage"
    col_list = ", ".join(columns)

    cur.execute(f"CREATE OR REPLACE TEMPORARY TABLE {stage_table} LIKE {table}")
    cur.executemany(
        f"INSERT INTO {stage_table} ({col_list}) VALUES ({', '.join(['%s'] * len(columns))})",
        rows,
    )

    on_clause = " AND ".join(f"target.{k} = source.{k}" for k in key)
    update_cols = [c for c in columns if c not in key]
    update_clause = ", ".join(f"target.{c} = source.{c}" for c in update_cols)
    insert_values = ", ".join(f"source.{c}" for c in columns)

    cur.execute(
        f"""
        MERGE INTO {table} AS target
        USING {stage_table} AS source
        ON {on_clause}
        WHEN MATCHED THEN UPDATE SET {update_clause}
        WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({insert_values})
        """
    )
    log.info("Merged %d rows into %s (Snowflake)", len(rows), table)


def load_to_snowflake() -> None:
    hud_rows = _read_processed("hud_fmr.json")
    acs_rows = _read_processed("acs_median_rent.json")
    lease_rows = _read_processed("synthetic_lease_concessions.json")

    conn = _snowflake_connect()
    try:
        cur = conn.cursor()
        try:
            _snowflake_merge(cur, "raw.hud_fmr", HUD_FMR_COLUMNS, HUD_FMR_KEY,
                              _rows_for_columns(hud_rows, HUD_FMR_COLUMNS))
            _snowflake_merge(cur, "raw.acs_median_rent", ACS_MEDIAN_RENT_COLUMNS, ACS_MEDIAN_RENT_KEY,
                              _rows_for_columns(acs_rows, ACS_MEDIAN_RENT_COLUMNS))
            _snowflake_merge(cur, "raw.synthetic_lease_concessions", SYNTHETIC_LEASE_COLUMNS, SYNTHETIC_LEASE_KEY,
                              _rows_for_columns(lease_rows, SYNTHETIC_LEASE_COLUMNS))
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

LOADERS = {
    "dev": load_to_postgres,
    "snowflake": load_to_snowflake,
}


def load_all(target: str) -> None:
    if target not in LOADERS:
        raise ValueError(f"Unknown load target {target!r}, expected one of {list(LOADERS)}")
    log.info("Loading processed data into target=%s", target)
    LOADERS[target]()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=list(LOADERS),
        default=os.environ.get("LOAD_TARGET", "dev"),
        help="Which raw schema to load into (default: $LOAD_TARGET or 'dev').",
    )
    return parser.parse_args()


if __name__ == "__main__":
    load_all(_parse_args().target)
