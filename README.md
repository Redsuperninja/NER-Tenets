# Dev sandbox (throwaway Postgres)

Prototyping environment for the raw → staging → analytics SQL, kept in the
repo to show the iteration process. **Not** what's deployed — the real
target is Snowflake (see `../sql/`).

## 1. Start the DB

```bash
./setup-dev.sh
```

Starts the sandbox (`docker compose -f dev/docker-compose.dev.yml up -d`)
and waits until it's healthy. On first start, everything in `sql/` runs
once in filename order: raw tables → staging views → analytics view →
seed data.

## 2. Load it with data

With the sandbox up, run the ETL pipeline (extract → transform → load)
against it via Docker, so nothing needs installing locally:

```bash
cp env.example .env   # fill in HUD_API_TOKEN and CENSUS_API_KEY — Snowflake vars aren't needed for the dev target
./run-etl.sh
```

This builds the `etl` image and runs `docker compose run --rm etl --target
dev`. `--target dev` points the load step at the sandbox container instead
of Snowflake. `docker-compose.yml` sets `DEV_DB_HOST=host.docker.internal`
so the ETL container can reach it on the host; credentials are the
sandbox's throwaway defaults (`ner_user` / `ner_db`) either way.

The load step upserts on each table's natural key —
`(county_fips, bedroom_count, fmr_year)`, `(county_fips, acs_year)`,
`lease_key` — so rerunning the pipeline is safe and won't duplicate rows.

To re-run just the load step without re-hitting the HUD/Census APIs (e.g.
after tweaking `dev/sql/`):

```bash
./run-etl.sh python etl/load.py --target dev
```

## 3. Verify the NER logic

```bash
docker exec -it ner-dev-db psql -U ner_user -d ner_db \
  -c "SELECT * FROM analytics.vw_net_effective_rent ORDER BY county_name, bedroom_count;"
```

You should see 5 rows (Denver x2, Boulder, El Paso, Larimer), each with
`net_effective_rent` ≤ `gross_rent`, and El Paso (no concessions) showing
`ner_discount_pct = 0`.

## 4. Tear down

```bash
docker compose -f dev/docker-compose.dev.yml down
```

No volume is defined, so this wipes all data — that's intentional; it's a
throwaway sandbox, not a persistent database.

## Porting to Snowflake

- `CREATE SCHEMA` / `TABLE` / `VIEW` syntax carries over almost as-is. Main
  differences: Snowflake-specific types (`NUMBER` vs `NUMERIC`) and
  warehouse/database context statements (`USE WAREHOUSE`, `USE DATABASE`)
  that Postgres has no equivalent for.
- `SERIAL` (Postgres auto-increment) becomes `IDENTITY` in Snowflake.
- Real `raw.*` tables in Snowflake are loaded by the ETL pipeline
  (`../etl/`), not manually seeded like `04_seed_sample_data.sql` here.