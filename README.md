# Dev sandbox (throwaway Postgres)

Prototyping environment for the raw → staging → analytics SQL, kept in the
repo to show the iteration process. This is **not** what's deployed — the
real target is Snowflake (see `../sql/`).

## Run it

```bash
docker compose -f docker-compose.dev.yml up -d
```

The container auto-runs everything in `sql/` in filename order on first
start: raw tables → staging views → analytics view → seed data.

## Verify the NER logic works

```bash
docker exec -it ner-dev-db psql -U dev -d ner_dev \
  -c "SELECT * FROM analytics.vw_net_effective_rent ORDER BY county_name, bedroom_count;"
```

You should see 5 rows (Denver x2, Boulder, El Paso, Larimer), each with a
`net_effective_rent` lower than or equal to `gross_rent`, and the El Paso
row (no concessions) showing `ner_discount_pct = 0`.

## Tear down

```bash
docker compose -f docker-compose.dev.yml down
```

No volume is defined, so this wipes all data — that's intentional, it's a
throwaway sandbox, not a persistent database.

## What changes when this is ported to Snowflake

- `CREATE SCHEMA` / `CREATE TABLE` / `CREATE VIEW` syntax is nearly
  identical — the main differences will be Snowflake-specific typing
  (e.g. `NUMBER` instead of `NUMERIC`) and warehouse/database context
  statements (`USE WAREHOUSE`, `USE DATABASE`) that Postgres has no
  equivalent for.
- `SERIAL` (Postgres auto-increment) becomes an `IDENTITY` column in
  Snowflake.
- The real `raw.*` tables in Snowflake are loaded by the ETL pipeline
  (`../etl/`), not manually seeded like `04_seed_sample_data.sql` here.