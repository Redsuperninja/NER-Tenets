#!/usr/bin/env bash
# End-to-end pipeline run against the throwaway dev Postgres sandbox:
#   1. start ner-dev-db (dev/docker-compose.dev.yml)
#   2. run extract -> transform -> load (raw -> staging -> analytics), all
#      inside the etl Docker image, targeting Postgres
#
# Usage: ./scripts/run-pipeline-dev.sh
set -euo pipefail

cd "$(dirname "$0")/.."

./scripts/setup-dev.sh
./scripts/run-etl.sh --target dev

echo "Dev pipeline complete. Query results in ner-dev-db (localhost:5432, ner_user/ner_db)."
