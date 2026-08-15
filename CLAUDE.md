# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository location

The git repository root is the nested `de_practicum_demo/` directory (it holds `.git`, `README.md`, `AGENTS.md`). The outer `c:\Code\de_practicum_demo` is only a container folder. Run all commands from the inner directory.

## Commands

Stack lifecycle (PowerShell wrapper over `scripts/stack-*.ps1`):

```powershell
.\stack.ps1 up | down | status
.\stack.ps1 build [-NoCache] [-Service jupyter]
.\stack.ps1 logs [-Service kafka] [-Tail 500] [-NoFollow]
.\stack.ps1 reset [-Force]     # DESTRUCTIVE: removes named volumes (Postgres, MinIO, Metabase, Iceberg catalog)
```

Compose files are layered and both are almost always needed together: `docker-compose.yml` (Postgres + Airflow) and `docker-compose.extended.yml` (MinIO, Spark, Kafka, Iceberg, Trino, BI, observability). `docker-compose.local-airflow.yml` is an offline fallback for the base stack only.

Python tooling is managed by uv 0.12.5 with Python 3.12. Create or refresh the
locked development environment from the repository root:

```bash
uv sync --locked
```

Regenerate every committed dependency lock after intentionally changing
`pyproject.toml` or a service `requirements.in` file with
`scripts/lock-python-dependencies.ps1` on Windows or
`scripts/lock-python-dependencies.sh` on macOS/Linux.

Tests — `pytest.ini` sets `addopts = -m "not integration and not e2e and not airflow"`, so the first command runs only the fast unit suite:

```bash
uv run --locked pytest                                      # fast unit suite (the PR gate)
uv run --locked pytest tests/test_writer.py::test_name      # single test
uv run --locked pytest tests --cov=iceberg --cov-fail-under=90   # exact CI gate
uv run --locked pytest tests/integration -m integration     # needs live MinIO + iceberg-rest + trino
uv run --locked pytest tests/e2e -m e2e                     # needs full stack (Kafka → Spark → lakehouse)
uv run --locked pytest tests/test_dags.py -m airflow        # runs DagBag inside the de-demo-airflow container
```

Markers are declared in `pytest.ini`: `integration`, `iceberg`, `trino`, `e2e`, `airflow`, `spike2`, `architecture`. `tests/conftest.py` puts `iceberg/` on `sys.path`, so services import as `writer.iceberg_writer`, `medallion.iceberg_medallion`, `common.ops`.

Lint (`pyproject.toml` pins the development tools; `.trunk/trunk.yaml` pins a broader set for `trunk check`):

```bash
uv run --locked ruff check .
uv run --locked black --check .
docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet
```

Non-pytest checkable surfaces: `scripts/doctor.{cmd,sh}` (host/Docker diagnostics), `scripts/run_checks.{cmd,sh}` (numbered SQL gates in `db/demo_sql/`, executed in the Postgres container), `scripts/build_report.{cmd,sh}`, `scripts/verify_maintenance_dag.py`.

## Architecture

Two independent pipelines share MinIO (S3) and PostgreSQL.

**Real-time lakehouse** (the part under active development):

```
orders-producer → Kafka(orders) → orders-streaming (Spark 4.2 Structured Streaming)
  ├→ Parquet landing  s3://de-practicum/streaming/orders_raw
  └→ upsert marts.streaming_orders (Postgres, monotonic on business_version)
landing → iceberg-writer (PyIceberg, 10s poll) → bronze.orders
bronze  → iceberg-medallion (60s) → silver.orders_clean → gold.orders_daily_metrics
Trino (iceberg catalog, REST) → Superset / Metabase
Airflow lakehouse_maintenance → Trino ALTER TABLE ... EXECUTE {optimize, expire_snapshots, remove_orphan_files}
```

**Batch Olist**: `data/raw/*.csv` → Airflow `demo_core_marts_pipeline` → Postgres `stg` → `core` → `marts` → HTML report.

Spark writes Iceberg *indirectly*: there is no `iceberg-spark-runtime-4.2` JAR, so Spark lands raw Parquet and PyIceberg ingests it. Do not "fix" this by adding a Spark Iceberg sink without checking runtime availability (rationale in `README.md`).

### Layer contracts — do not change silently

- **Landing** — raw Parquet as written by Spark; uncurated, may contain replays.
- **Bronze** (`bronze.orders`) — 1:1 from landing, partitioned by `event_date`, one snapshot per ingest batch.
- **Silver** (`silver.orders_clean`) — one row per `order_id`, highest `kafka_offset` wins.
- **Gold** (`gold.orders_daily_metrics`) — aggregates by `event_date` / `country` / `status`.

### Idempotency and recovery invariants

- Writer appends carry `snapshot_properties={"load-id": ...}`; recovery re-checks `pending` load-ids against the table's snapshot summaries and skips re-append if already committed. State lives in `/state/ingested.json` (`done` + `pending`). See `iceberg/writer/iceberg_writer.py`.
- The writer retries on `CommitFailedException` — concurrent maintenance can legitimately cause commit conflicts.
- E2E tests are hermetic: per-run Kafka topic, landing prefix, Iceberg namespace, and a separate `e2e` Postgres database. The canonical `dwh` database is asserted to be untouched. Failures preserve a bundle under `artifacts/e2e-logs/<run_id>/`.

### B2 rollout state machine

The medallion is mid-migration between a legacy full-rebuild Silver and the incremental "B2" path. Three env vars form a **validated** state machine in `iceberg/common/cutover.py` (`RUNTIME_ROLLOUT_MATRIX`), enforced at startup by `validate_runtime_config()`; any other combination raises:

| `SILVER_MODE` | `GOLD_SOURCE` | `SHADOW_COMPARE` | rollout |
|---|---|---|---|
| legacy | legacy | 0 | legacy |
| b2 | legacy | 0 | rollback |
| b2 | legacy | 1 | shadow |
| b2 | persisted_silver | 1 | cutover |

Persisted Silver must never become the Gold source with shadow validation off. In shadow mode the medallion pins a Bronze snapshot boundary first so the legacy candidate and the B2 result describe the same logical source — a live Bronze re-scan would race ingestion and produce bogus evidence. A shadow mismatch raises and records `status="shadow_failed"`.

### Observability

`iceberg/common/ops.py` `Metrics.record()` writes one best-effort row per writer batch / medallion cycle to `marts.lakehouse_metrics` (auto-DDL, `METRICS_ENABLED=0` disables). A Postgres failure is logged and must never break ingestion. `marts.maintenance_runs` holds before/after snapshot counts from the maintenance DAG.

## Working rules

`AGENTS.md` is the authoritative repository instruction file; `ORCHESTRATION.md` describes the anti-overengineering workflow ladder (`minimal-design` → implementation → tests → `simplicity-challenge`, escalating for stateful/architectural changes). The architecture-audit skills in `.claude/skills/` implement that ladder.

- Treat Docker, Kafka, Spark, MinIO, Postgres, and Iceberg as stateful. Read-only analysis must not start/stop services, roll checkpoints, publish Kafka records, or mutate Iceberg tables.
- Credentials come from `.env` only. `trino/etc/catalog/iceberg.properties` is **generated at container startup** from `iceberg.properties.template` by `trino/etc/start-trino.sh`; edit the template, not the generated file.
- Behavior changes must land with focused tests plus updates to `README.md` and the relevant `docs/` file — those are the project contract.
- `.planning/` holds GSD workflow state (`STATE.md`, `ROADMAP.md`, phase plans). Generated audit reports under `.architecture-audit/` and `docs/architecture-audit/` are evidence, not contracts.
