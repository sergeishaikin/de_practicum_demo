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
- Run Python tools through the locked project environment with
  `uv run --locked`. `pytest.ini` excludes tests requiring the live stack; use
  the explicit `integration`, `iceberg`, `trino`, `e2e`, or `airflow` markers
  only when their dependencies are available.
- When changing a pipeline or schema, update focused tests and the applicable
  documentation. Prefer deterministic, idempotent tests over live-state tests
  unless a live integration is the requirement being verified.

## Verification contract

This section is the canonical repository policy for deciding when a change is
verified. The completion gate below must pass before a change is handed off.

During iteration, use the narrowest relevant check. Run the completion gate
only when the implementation is ready.

Before completing any non-documentation Python change, run:

```bash
uv run --locked ruff check .
uv run --locked black --check .
uv run --locked pytest
```

The existing CI workflow also defines this coverage check:

```bash
uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90
```

At the time this contract was adopted, that command had a known baseline gap:
all 150 fast tests passed, but total `iceberg` coverage was 79.80% against the
90% threshold, so the command exited with status 1. Report this known failure
when the coverage check is run. Do not lower the threshold or add unrelated
tests as part of another change; coverage remediation must be an explicit task.

Run additional checks according to the changed surface:

- DAG changes: `uv run --locked ruff check dags --select AIR3 --preview`.
- Compose or runtime configuration changes:
  `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet`.
- Airflow runtime changes: run
  `uv run --locked pytest tests/test_h1_runtime.py`, validate DAG imports with
  `uv run --locked pytest tests/test_dags.py -m airflow`, and perform a short
  scheduler, triggerer, and DAG-processor health smoke.
- Dependency input changes: regenerate the existing committed lock files with
  the repository lock script and verify the resulting diff.
- Streaming, schema, recovery, or other stateful changes: run only the
  relevant integration or E2E gate when its live dependencies are available
  and the task authorizes state mutation.

Documentation-only changes do not require the Python completion gate unless
they change executable commands or configuration examples.

When handing off a change, report the exact checks that ran and any live checks
that were skipped. Do not claim a check passed unless it was executed.

Do not add a test framework, task runner, wrapper script, or verification layer
unless the requested change explicitly requires it.

## Documentation

`README.md` and the relevant files under `docs/` are the project contract for
setup, architecture, configuration, deployment, and testing. Keep them aligned
with behavior changes. Generated audit reports and analysis artifacts are
evidence and references; they do not override the repository's runtime,
development, or documentation contracts.
