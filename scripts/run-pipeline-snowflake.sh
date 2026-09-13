#!/usr/bin/env bash
# End-to-end pipeline run against real Snowflake:
#   1. one-time warehouse/database/schema setup (sql/00_setup.sql), via snowsql
#      if it's installed -- safe to rerun, every statement is idempotent
#   2. run extract -> transform -> load (raw -> staging -> analytics), all
#      inside the etl Docker image, targeting Snowflake
#
# Requires .env with SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_PAT
# (a Programmatic Access Token, not a password -- see env.example).
#
# Usage: ./scripts/run-pipeline-snowflake.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found -- copy env.example to .env and fill in Snowflake credentials first." >&2
  exit 1
fi

# Load .env into this shell so snowsql (below) and run-etl.sh (via
# docker compose's env_file) both see the same Snowflake credentials.
set -a
source .env
set +a

export SNOWFLAKE_PASSWORD="$SNOWFLAKE_PAT"

: "${SNOWFLAKE_ACCOUNT:?SNOWFLAKE_ACCOUNT must be set in .env}"
: "${SNOWFLAKE_USER:?SNOWFLAKE_USER must be set in .env}"
: "${SNOWFLAKE_PAT:?SNOWFLAKE_PAT must be set in .env (a Programmatic Access Token)}"

if command -v snowsql >/dev/null 2>&1; then
snow sql --temporary-connection \
    --account "$SNOWFLAKE_ACCOUNT" \
    --user "$SNOWFLAKE_USER" \
    --role "$SNOWFLAKE_ROLE" \
    --filename sql/00_setup.sql
else
  echo "snowsql not found on PATH -- skipping sql/00_setup.sql." >&2
  echo "Run it once yourself (or via the Snowflake UI) before continuing if the" >&2
  echo "NER_DEMO_WH warehouse / NER_DEMO database don't exist yet." >&2
fi

./scripts/run-etl.sh --target snowflake

echo "Snowflake pipeline complete."
