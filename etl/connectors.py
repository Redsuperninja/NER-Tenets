"""
etl/connectors.py

Shared connection helpers for the two load targets, so anything that needs
a raw DB connection (etl/load.py, etl/run_query.py, ad hoc scripts) doesn't
duplicate the connect/auth logic.
"""

from __future__ import annotations

import os
from pathlib import Path


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def postgres_connect():
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


def snowflake_connect():
    import snowflake.connector

    return snowflake.connector.connect(
        account=_require_env("SNOWFLAKE_ACCOUNT"),
        user=_require_env("SNOWFLAKE_USER"),
        token=_require_env("SNOWFLAKE_PAT"),
        authenticator="PROGRAMMATIC_ACCESS_TOKEN",
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "NER_DEMO_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "NER_DEMO"),
        role=os.environ.get("SNOWFLAKE_ROLE") or None,
        schema="RAW",
    )


def snowflake_execute_sql_file(cur, path: Path) -> None:
    without_comments = "\n".join(
        line.split("--", 1)[0] for line in path.read_text().splitlines()
    )
    statements = [s.strip() for s in without_comments.split(";") if s.strip()]
    for statement in statements:
        cur.execute(statement)


CONNECTORS = {
    "dev": postgres_connect,
    "snowflake": snowflake_connect,
}


def connect(target: str):
    if target not in CONNECTORS:
        raise ValueError(f"Unknown target {target!r}, expected one of {list(CONNECTORS)}")
    return CONNECTORS[target]()
