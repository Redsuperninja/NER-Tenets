# NER Tenets

ETL pipeline that computes Net Effective Rent (NER) for Colorado counties:
extracts HUD Fair Market Rent + Census ACS median rent data (plus simulated
lease concessions, since no public source exists for that), loads it into a
`raw → staging → analytics` schema, and answers NER queries against it.

Two load targets share the same pipeline code and the same schema shape:

- **`dev`** — a throwaway local Postgres sandbox, for iterating on the SQL
  cheaply before touching real Snowflake credits.
- **`snowflake`** — the real target.

## Project layout

```
etl/                  extract.py -> transform.py -> load.py, orchestrated by run_pipeline.py
  connectors.py        shared Postgres/Snowflake connection helpers
  run_query.py          runs an ad hoc .sql file against either target, prints results
sql/                  Snowflake DDL: 00_setup (warehouse/db/schemas) -> 01_raw -> 02_staging -> 03_analytics
dev/
  docker-compose.dev.yml   throwaway Postgres sandbox
  sql/                     dev/Postgres equivalent of sql/ (raw.sql, staging.sql, analytics.sql)
  sql/queries/             example NER queries, written against analytics.vw_net_effective_rent
scripts/              thin wrappers around the Docker/pipeline commands below
```

## Setup

```bash
cp env.example .env
```

Fill in:
- `HUD_API_TOKEN` / `CENSUS_API_KEY` — needed for extract, regardless of target.
- `SNOWFLAKE_ACCOUNT` / `SNOWFLAKE_USER` / `SNOWFLAKE_PAT` — only needed for
  the `snowflake` target. `SNOWFLAKE_PAT` is a **Programmatic Access Token**
  (Snowsight → user menu → Profile → Programmatic access tokens), not your
  login password — `load.py` authenticates with
  `authenticator=PROGRAMMATIC_ACCESS_TOKEN`.

Everything runs inside Docker (`docker-compose.yml` builds the `etl` image),
so nothing needs installing locally beyond Docker itself.

## Running the pipeline end to end

```bash
./scripts/run-pipeline-dev.sh          # dev Postgres sandbox
./scripts/run-pipeline-snowflake.sh    # real Snowflake
```

Each script starts/prepares its target, then runs extract → transform →
load. The Snowflake variant also runs the one-time `sql/00_setup.sql`
(warehouse/database/schema creation, safe to rerun) via `snowsql` first, if
it's installed.

Under the hood both call `./scripts/run-etl.sh --target <dev|snowflake>`,
which builds the `etl` image and runs
`docker compose run --rm etl --target <target>`. That in turn runs
`etl/run_pipeline.py`, which:

1. **extract** — pulls HUD FMR + ACS data, writes JSON to `etl/data/raw/`.
2. **transform** — cleans it into `raw.hud_fmr` / `raw.acs_median_rent`
   shapes and generates the synthetic lease concessions table.
3. **load** — ensures raw tables exist (`sql/01_raw.sql` /
   `dev/sql/raw.sql`), upserts/merges rows on each table's natural key
   (`(county_fips, bedroom_count, fmr_year)`, `(county_fips, acs_year)`,
   `lease_key`), then rebuilds staging + analytics from
   `sql/02_staging.sql` + `sql/03_analytics.sql` (or the `dev/sql/`
   equivalents).

Reruns never duplicate rows, so the whole pipeline is safe to run repeatedly.

To re-run just the load step without re-hitting the HUD/Census APIs:

```bash
./scripts/run-etl.sh python etl/load.py --target dev
./scripts/run-etl.sh python etl/load.py --target snowflake
```

## Querying results

`dev/sql/queries/` has example NER queries (by value, by percent, by county,
etc.), all written against `analytics.vw_net_effective_rent`. That view has
the identical shape in both targets, so the same query file runs unmodified
against either one:

```bash
./scripts/run-query.sh dev/sql/queries/NER_BY_VALUE.sql --target snowflake
./scripts/run-query.sh dev/sql/queries/NER_BY_VALUE.sql --target dev
```

This runs `etl/run_query.py` in the same Docker image/credentials as the
pipeline and prints the results as a plain table.

**Current state / automation TODO:** getting new query files into Snowflake
today just means running `run-query.sh` against them by hand as they're
written — there's no scheduled or CI-triggered run. If these queries need to
run on a schedule (a daily NER report, say) or get exposed somewhere besides
a terminal, that's a natural next step: either add a `--output csv/json`
mode to `run_query.py` and drop that into a cron/GitHub Actions job, or wire
the query set into `run_pipeline.py` so a pipeline run also regenerates a
fixed set of reports.

## Verifying the dev sandbox directly

```bash
./scripts/setup-dev.sh
docker exec -it ner-dev-db psql -U ner_user -d ner_db \
  -c "SELECT * FROM analytics.vw_net_effective_rent ORDER BY county_name, bedroom_count;"
./scripts/teardown-dev.sh   # wipes it -- no volume is defined, that's intentional
```

## Porting dev SQL to Snowflake

`dev/sql/` is a prototyping ground for the `sql/` files, not a second
maintained copy — when changing the schema, edit both, mirroring the
differences below:

- `CREATE SCHEMA` / `TABLE` / `VIEW` syntax carries over almost as-is. Main
  differences: Snowflake-specific types (`NUMBER`/`VARCHAR` vs
  `NUMERIC`/`TEXT`), `UUID_STRING()` vs Postgres's `gen_random_uuid()`, and
  warehouse/database context statements (`USE WAREHOUSE`, `USE DATABASE`)
  that Postgres has no equivalent for.
- Real `raw.*` tables in Snowflake are loaded by the ETL pipeline
  (`etl/load.py`), not manually seeded.
