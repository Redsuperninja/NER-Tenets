#!/usr/bin/env bash
# Run a .sql file (e.g. dev/sql/queries/*.sql) against dev or snowflake and
# print the results, using the same etl Docker image/credentials as the
# pipeline scripts.
#
# Usage:
#   ./scripts/run-query.sh dev/sql/queries/NER_BY_VALUE.sql --target snowflake
#   ./scripts/run-query.sh dev/sql/queries/NER_BY_VALUE.sql --target dev
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo ".env not found -- copy env.example to .env and fill in credentials first." >&2
  exit 1
fi

docker compose build etl >/dev/null
docker compose run --rm --entrypoint python etl etl/run_query.py "$@"
