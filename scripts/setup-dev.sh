#!/usr/bin/env bash
# Start the throwaway dev Postgres sandbox (raw -> staging -> analytics,
# seeded from sql/ on first start) and wait until it's ready for connections.
set -euo pipefail

docker compose -f dev/docker-compose.dev.yml up -d

echo "ner-dev-db is up on localhost:5432 (ner_user/ner_db)."
