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

`pyproject.toml` sets `required-version = "==0.12.5"` — an **exact** pin, so any
other uv version refuses to run and `uv lock --check` exits 2 with a version
error rather than a lock error. Install exactly 0.12.5, or prefix commands with
`uvx --from uv==0.12.5 uv ...`.

Regenerate every committed dependency lock after intentionally changing
`pyproject.toml` or a service `requirements.in` file with
`scripts/lock-python-dependencies.ps1` on Windows or
`scripts/lock-python-dependencies.sh` on macOS/Linux.

### Invoking dbt — always through a project venv

**Bare `dbt` on this machine resolves to an unrelated Anaconda installation**
(`C:\Users\serge\anaconda3\Scripts\dbt`), which carries its own dbt-core version
and only the Trino adapter. Running it against `dbt/warehouse` fails on a
missing `postgres` adapter, and running it anywhere else silently uses a version
the repository does not pin. Always call dbt through the project's own venv:

| Project | Executable | Runtime |
|---|---|---|
| `dbt/warehouse` (`warehouse_transform`, PostgreSQL) | `.venv-dbt-warehouse\Scripts\dbt.exe` | dbt-core 1.12.2 + dbt-postgres 1.11.0 |
| `dbt` (`lakehouse_semantic`, Trino) | `.venv-dbt\Scripts\dbt.exe` | dbt-core 1.12.2 + dbt-trino 1.10.3 |

Restore or repair either environment from its committed hash-pinned
requirements file — never by installing dbt packages into Anaconda or any other
global Python:

```powershell
uv pip sync --python .venv-dbt\Scripts\python.exe --require-hashes dbt\requirements.txt
uv pip sync --python .venv-dbt-warehouse\Scripts\python.exe --require-hashes dbt\warehouse\requirements.txt
```

A plain `pip install dbt-core` / `dbt-postgres` now resolves to the Fusion-era
`dbt-core` 2.x line, which rejects the `postgres` adapter outright. The
`--require-hashes` sync above avoids that by construction.

Static typing is enforced by `uv run --locked mypy` over the scope declared in
`pyproject.toml` (`[tool.mypy] files`), currently `iceberg/`. `iceberg/` is a
`sys.path` root rather than a package, so the config sets `mypy_path`,
`explicit_package_bases` and `namespace_packages`; without them mypy resolves
`common/ops.py` under two module names and checks nothing.

Follow the canonical **Verification contract** in `AGENTS.md`. It defines the
completion gate, change-specific checks, stateful-test boundary, and required
verification evidence; do not maintain a separate gate in this file.

Test markers are declared in `pytest.ini`: `integration`, `iceberg`, `trino`,
`e2e`, `airflow`, `spike2`, and `architecture`. `tests/conftest.py` puts
`iceberg/` on `sys.path`, so services import as `writer.iceberg_writer`,
`medallion.iceberg_medallion`, and `common.ops`.

Non-pytest checkable surfaces: `scripts/doctor.{cmd,sh}` (host/Docker diagnostics), `scripts/run_checks.{cmd,sh}` (numbered SQL gates in `db/demo_sql/`, executed in the Postgres container), `scripts/build_report.{cmd,sh}`, `scripts/verify_maintenance_dag.py`, `scripts/validate_runtime_config.py`, `scripts/bootstrap_stack.py`.

## Dependency management

Two parallel locking mechanisms, both generated — **never hand-edit a generated file**:

- **Host dev environment** — `pyproject.toml` (`dev` dependency group) → `uv.lock` → exported to `requirements-dev.txt`.
- **Runtime and tool locks** — `airflow.requirements.in`, the service inputs under `iceberg/`, `jupyter/`, `kafka/producer/`, `observability/`, and `spark/`, plus the separate `dbt/requirements.in`, are compiled by `uv pip compile --universal --generate-hashes` into sibling `requirements.txt` files. Every custom Python Dockerfile installs with `--require-hashes` from a uv binary pinned by digest (`ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844…`, identical across all six).

`ci-pr.yml` reruns the lock script and does `git diff --exit-code` across all nine generated lock/export files, so a stale lock fails the PR.

Three exceptions worth knowing before editing an image:

- **Airflow** compiles with `--constraint airflow.constraints.txt`, a hand-maintained compatibility subset from Airflow 3.3.1's own Python 3.12 constraints; the base image digest fixes the rest of that environment.
- **Jupyter** no longer uses conda — `uv venv --python 3.10.21` builds the `spark420` env at the old conda path.

## CI

Six workflows, all installing uv 0.12.5 via a SHA-pinned `astral-sh/setup-uv`:

| Workflow | Trigger | Scope |
|---|---|---|
| `ci-pr.yml` | PR + push to `main` | Lint, compose validation, stale-lock check, fast suite with the 90% `iceberg/` coverage gate, Airflow DagBag |
| `ci-integration.yml` | manual + push to `main` | Live MinIO/REST-catalog/Trino integration layer |
| `ci-nightly.yml` | 02:15 UTC | Full stack, integration, deterministic E2E, maintenance DAG |
| `ci-m5-gates.yml` | PR touching `iceberg/**` or `tests/test_*.py` | M3/M4 recovery and cutover gates on a minimal Iceberg stack |
| `ci-h1-clean.yml` | manual + PR touching runtime env | Clean reproducible-runtime rebuild |
| `ci-s1-dbt.yml` | manual + PR touching `dbt/**` | dbt parse/compile/docs + Trino contract fixture |

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

**Batch Olist**: `data/raw/*.csv` → manual Airflow `warehouse_orders_ingestion` → Postgres `stg`/`core` → `core.orders` Asset → automatic `warehouse_marts_validation` → marts views/audit → HTML report.

Spark writes Iceberg *indirectly*: there is no `iceberg-spark-runtime-4.2` JAR, so Spark lands raw Parquet and PyIceberg ingests it. Do not "fix" this by adding a Spark Iceberg sink without checking runtime availability (rationale in `README.md`).

### Layer contracts — do not change silently

- **Landing** — raw Parquet as written by Spark; uncurated, may contain replays.
- **Bronze** (`bronze.orders`) — 1:1 from landing, partitioned by `event_date`, one snapshot per ingest batch.
- **Silver** (`silver.orders_clean`) — one row per `order_id`, highest `business_version` wins; transport order never decides. Executable contract: `tests/features/silver_business_state.feature`.
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

`iceberg/common/ops.py` `Metrics.record()` writes best-effort rows to `marts.lakehouse_metrics` (auto-DDL, `METRICS_ENABLED=0` disables): one per writer batch, and per medallion cycle one row for each executed phase (`b2`, `shadow`, `gold`) plus a `cycle` envelope row written last, all sharing a `cycle_id`. Totals must filter `phase = 'cycle' or phase is null` or they double-count; `classify_metric_row` classifies the pre-phase rows. A Postgres failure is logged and must never break ingestion. `marts.maintenance_runs` holds before/after snapshot counts from the maintenance DAG.

## Working rules

`AGENTS.md` is the authoritative repository instruction file; `ORCHESTRATION.md` describes the anti-overengineering workflow ladder (`minimal-design` → implementation → tests → `simplicity-challenge`, escalating for stateful/architectural changes). The architecture-audit skills in `.claude/skills/` implement that ladder.

- Treat Docker, Kafka, Spark, MinIO, Postgres, and Iceberg as stateful. Read-only analysis must not start/stop services, roll checkpoints, publish Kafka records, or mutate Iceberg tables.
- Credentials come from `.env` only. `trino/etc/catalog/iceberg.properties` is **generated at container startup** from `iceberg.properties.template` by `trino/etc/start-trino.sh`; edit the template, not the generated file.
- Behavior changes must land with focused tests plus updates to `README.md` and the relevant `docs/` file — those are the project contract.
- Planning lives in `openspec/` (see the Planning methodology section of `AGENTS.md`): `openspec/specs/` for standing capabilities, `openspec/changes/` for proposals in flight, `openspec/backlog/` for specified but **unauthorised** work. A backlog item authorises nothing and is not evidence of current behaviour — starting one means opening the change its index row names. The NG-0.1 … NG-2.2 next-generation package lives in `openspec/backlog/next-generation/`.
- `.planning/` holds the frozen GSD execution record (`STATE.md`, `ROADMAP.md`, phase plans) for Phases 1-4. It is historical evidence, not a work queue; unexecuted obligations and their OpenSpec successors are mapped in `.planning/STATE.md`. Generated audit reports under `.architecture-audit/` and `docs/architecture-audit/` are evidence, not contracts.
