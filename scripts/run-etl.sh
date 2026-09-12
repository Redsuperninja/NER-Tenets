#!/usr/bin/env bash
# Build and run the ETL pipeline (extract -> transform -> load) in Docker
# against the dev sandbox. Pass extra args to forward them to
# etl/run_pipeline.py, e.g.:
#   ./run-etl.sh --target snowflake
set -euo pipefail

if [ ! -f .env ]; then
  echo ".env not found -- copy env.example to .env and fill in HUD_API_TOKEN / CENSUS_API_KEY first." >&2
  exit 1
fi

docker compose build etl

if [ "$#" -eq 0 ]; then
  docker compose run --rm etl --target dev
else
  docker compose run --rm etl "$@"
fi
