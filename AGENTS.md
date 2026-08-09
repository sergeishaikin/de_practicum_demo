# DE Practicum — repository instructions

## Scope

This repository is a local Docker Compose data-engineering platform. Keep
changes specific to this project; do not import instructions or workflows from
other repositories.

## Architecture

- Airflow orchestrates scheduled pipelines and maintenance DAGs.
- Spark 4.2 handles batch/stream processing and writes raw Parquet to the
  MinIO landing area.
- The PyIceberg writer ingests landing files into the Iceberg REST catalog and
  `bronze.orders`.
- The medallion job derives `silver.orders_clean` and
  `gold.orders_daily_metrics` from Bronze.
- Trino queries Iceberg tables and runs maintenance procedures; PostgreSQL
  stores relational metadata and operational metrics.
- Kafka is the streaming input boundary. Preserve offset, checkpoint,
  idempotency, and replay/recovery semantics when changing streaming code.

The landing, Bronze, Silver, and Gold layers have different contracts. Do not
silently change schemas, deduplication rules, snapshot behavior, or ownership
of a layer without updating the relevant documentation and tests.

## Runtime safety

- Treat Docker, Kafka, Spark, MinIO, PostgreSQL, and Iceberg as stateful
  systems.
- Read-only analysis must not start/stop services, roll checkpoints, publish
  Kafka records, or mutate Iceberg tables.
- Use `stack.ps1 reset` only when explicitly requested; it removes persisted
  local Docker volumes and data.
- Keep secrets in `.env`/environment variables. Never hard-code credentials or
  commit local runtime state.
- For recovery or cutover work, identify the owner of each state transition
  and verify the checkpoint/offset/snapshot evidence before proceeding.

## Development and tests

- Use the documented Compose files and commands in `README.md` and `docs/`.
- Start the local stack with `stack.ps1 up` (or the documented Compose
  equivalent), and inspect it with `stack.ps1 status` and `stack.ps1 logs`.
- Run the default unit/fast suite with `pytest`. `pytest.ini` excludes tests
  requiring the live stack; use the explicit `integration`, `iceberg`,
  `trino`, `e2e`, or `airflow` markers only when their dependencies are
  available.
- When changing a pipeline or schema, update focused tests and the applicable
  documentation. Prefer deterministic, idempotent tests over live-state tests
  unless a live integration is the requirement being verified.

## Documentation

`README.md` and the relevant files under `docs/` are the project contract for
setup, architecture, configuration, deployment, and testing. Keep them aligned
with behavior changes. Generated audit reports and analysis artifacts are
evidence and references; they do not override the repository's runtime,
development, or documentation contracts.
