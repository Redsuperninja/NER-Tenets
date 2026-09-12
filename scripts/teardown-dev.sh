#!/usr/bin/env bash
# Tear down the dev Postgres sandbox. No volume is defined, so this wipes
# all data -- that's intentional, it's a throwaway sandbox.
set -euo pipefail

docker compose -f dev/docker-compose.dev.yml down
