<!-- generated-by: gsd-doc-writer -->
# Development

## Local setup

The runtime is the Docker Compose stack used for the demo. Host-side Python
development uses `uv` 0.12.5, Python 3.12, and the committed `uv.lock`. Install
the exact uv version, fork and clone the repository, then create the locked
environment. On Windows:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.12.5/install.ps1 | iex"
uv --version
uv sync --locked
```

On macOS/Linux:

```bash
curl -LsSf https://astral.sh/uv/0.12.5/install.sh | sh
uv --version
uv sync --locked
```

Both version checks must report `uv 0.12.5`. If changing the host installation
is undesirable, run a project command through the exact tool version, for
example `uvx --from uv==0.12.5 uv sync --locked`.

Run host tools through the managed environment, for example `uv run --locked
pytest` and `uv run --locked ruff check .`. Then create the runtime settings:

```powershell
Copy-Item .env.example .env
```

Add `SUPERSET_SECRET_KEY` to `.env` if you work on Superset (see [CONFIGURATION.md](CONFIGURATION.md)).

Build the locally-built images and start the stack:

```powershell
.\stack.ps1 build
.\stack.ps1 up
```

The locally-built images are: `de-practicum-demo-airflow:0.1.0` (from `airflow.Dockerfile`), the Spark images (`spark/Dockerfile`, used by `spark-master`, `spark-worker`, `spark-connect`, `orders-streaming`), the Jupyter image (`jupyter/Dockerfile`), and the PyIceberg image (`iceberg/Dockerfile`, used by `iceberg-writer` and `iceberg-medallion`).

Interactive work happens inside Jupyter (`http://localhost:18888`, token via `docker exec de-demo-jupyter jupyter server list`) or by executing jobs inside the containers. Python sources for the writer, medallion, producer, and Spark jobs are mounted into their containers as read-only volumes, so editing a file on the host takes effect after restarting the service.

## Build commands

| Command | Description |
|---|---|
| `.\stack.ps1 up` | Start all services from both Compose files. |
| `.\stack.ps1 down` | Stop services, keep named volumes. |
| `.\stack.ps1 build` | Build the locally-built images. |
| `.\stack.ps1 build -NoCache` | Rebuild images without layer cache. |
| `.\stack.ps1 build -Service jupyter` | Rebuild a single image. |
| `.\stack.ps1 status` | Show container status (`docker compose ps -a`). |
| `.\stack.ps1 logs` | Follow logs for all services. |
| `.\stack.ps1 logs -Service kafka` | Follow logs for one service. |
| `.\stack.ps1 logs -Service spark-worker -Tail 500` | Show the last 500 lines. |
| `.\stack.ps1 logs -Service spark-worker -NoFollow` | Show logs without following. |
| `.\stack.ps1 reset` | Destroy named volumes (interactive, type `RESET`). |
| `.\stack.ps1 reset -Force` | Destroy named volumes non-interactively. |

Equivalent direct Compose form used by the scripts:

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml -f .\docker-compose.extended.yml <command>
```

## Code style

- Python formatting and linting are pinned in the `dev` dependency group. Run `uv run --locked ruff check .` and `uv run --locked black --check .`.
- The Airflow DAGs use the stable Airflow 3 Task SDK imports (`airflow.sdk`: `Asset`, `Metadata`, `@dag`, `@task`, and `TaskGroup`).
- A `dags/.mypy_cache` directory indicates mypy has been used; run it manually when changing the DAG.

## Branch conventions

No explicit convention is documented (`CONTRIBUTING.md` and `.github/PULL_REQUEST_TEMPLATE.md` do not exist). The repository's recent history uses topic branches prefixed with `feature/`, e.g. `feature/extended-local-stack`. Follow that pattern (`feature/<short-name>`) unless a convention is added.

## PR process

No pull-request template or review workflow is defined. The default process applies:

1. Fork the repository and create a topic branch.
2. Make the change; verify the relevant pipeline still runs (see [TESTING.md](TESTING.md)).
3. Open a pull request describing what changed and how it was verified.

## Component deep dives

### Airflow orchestration

The batch pipeline lives in `dags/warehouse_orders.py` and is built on the Airflow 3.3.1 image from `airflow.Dockerfile` (Python 3.12, `psycopg2-binary==2.9.12`). Both DAGs allow one active run and have explicit task timeouts, zero retries, owners, structured tags, descriptions, display names, and `doc_md`:

- `load_raw_csv_to_stg` truncates `stg.*` and copies the CSV files from `data/raw/` via `COPY ... FROM stdin`.
- `validate_staging` parses the four CSVs with Python's `csv` module and requires each non-empty data-row count to exactly match the corresponding staging table before any core/marts mutation.
- `core.rebuild_core` executes the unchanged `db/pipeline_sql/10_rebuild_core.sql`, which still owns core tables and marts views in one transaction.
- `core.validate_core` only checks queryability and collects row counts. The terminal publisher emits `core.orders`/`core.order_items` events only after all ingestion predecessors succeed.
- The successful `core.orders` event automatically schedules `warehouse_marts_validation`; no code manually triggers it.
- `quality.check_payment_reconcile` preserves the `0.01` payment rule. `publication.write_audit` keeps the downstream DagRun ID as `marts.pipeline_runs.run_id` and stores the source event's `source_dag_run.run_id` in nullable `ingestion_run_id`.

The tasks publish Airflow Assets for the managed raw CSV, `stg`, `core`,
`marts`, and audit objects. These Assets document the batch lineage only; they
do not claim ownership of external streaming or Iceberg events. The
`core.orders` Asset additionally provides the real orchestration boundary.

The base stack is defined in `docker-compose.yml`; the same service is available in `docker-compose.local-airflow.yml` using a pre-built local image (`local/airflow:3.3.1-lab`, `pull_policy: never`) as an offline fallback. The Airflow container uses `airflow standalone`, LocalExecutor with parallelism `4`, and the dedicated `airflow_meta` database in PostgreSQL. The idempotent `airflow-db-init` service provisions the database before Airflow starts, so metadata survives container recreation. Simple Auth Manager runs in all-admin mode with no login prompt, and the named UI is bound only to `127.0.0.1`.

The SQL behind the layers (`stg` → `core` → `marts`) lives in `db/`. PostgreSQL
runs `db/init/` when its volume is first created. For an existing volume,
`scripts/bootstrap_stack.py` applies the idempotent warehouse provenance
migration as well as the Airflow metadata bootstrap; no volume reset is
required for `ingestion_run_id`.

### Spark jobs

All Spark jobs run on the `apache/spark:4.2.0-java21-python3` image (`spark/Dockerfile`, which adds `psycopg2-binary` and `boto3`):

- `spark/jobs/orders_streaming.py` — the real-time job. Reads the `orders` topic with `from_json` against an explicit schema, filters null `order_id`, adds `event_date`, and starts two `writeStream` queries with a 10-second trigger: Parquet into `s3://de-practicum/streaming/orders_raw` (partitioned by `event_date`) and a `foreachBatch` upsert into `marts.streaming_orders` via JDBC.
- `spark/jobs/build_mart.py` — a small batch job that reads `raw.orders` from Postgres via JDBC and writes `marts.sales_daily` (`orders_count`, `revenue` grouped by `sales_date`).
- `spark/jobs/verify_bronze_orders.py` — an introspection job that lists Iceberg tables in `iceberg.bronze`, prints the `bronze.orders` schema and snapshot history, and demonstrates time travel with `version as of`.

The streaming job is deployed as the `orders-streaming` Compose service. Classic Spark and Spark Connect both connect to `spark://spark-master:7077`; classic mode is covered in the README under "Spark modes".

### Kafka data generation

`kafka/producer/orders_producer.py` is a `confluent-kafka` producer (`confluent-kafka==2.15.0`, baked into its image from a hash-locked file) that publishes one synthetic order per `1 / EVENTS_PER_SECOND` seconds. Events are JSON with `order_id` (UUID), `customer`, `amount`, `country`, `status`, and `event_time`. Messages use `order_id` as the partition key with `acks=all` and idempotence enabled. It runs as the `orders-producer` service against `kafka:9092` (topic `orders`, 3 partitions, created manually or via Kafka UI).

### PyIceberg writer and medallion

Both services share the `iceberg/Dockerfile` image (`python:3.12-slim` with `pyiceberg[pyarrow]`) and the `iceberg/common/ops.py` metrics helper. Both mount the whole `iceberg/` directory as a read-only volume, so edits to the shared `ops.py` also take effect on restart:

- `iceberg/writer/iceberg_writer.py` — polls `s3://de-practicum/streaming/orders_raw`, waits for files to settle, records them in `/state/ingested.json` under a new `load-id`, appends them to `bronze.orders` with the `load-id` in the snapshot summary, then marks the files done. On startup it reconciles `pending` load-ids against the table's snapshot summaries so committed batches are never re-appended. A commit that races another writer/maintenance (`CommitFailedException`) is retried up to `MAX_APPEND_ATTEMPTS`. `SIMULATE_CRASH_AFTER_COMMIT=1` / `SIMULATE_CRASH_BEFORE_COMMIT=1` force a simulated crash for demos.
- `iceberg/medallion/iceberg_medallion.py` — every `MEDALLION_INTERVAL_SECONDS` it reads all of `bronze.orders`, runs PyArrow quality assertions (`QUALITY_VALID_STATUSES`, null/positive `amount`, non-null `order_id`/`country`/`event_time`), then overwrites `silver.orders_clean` (deduplicated by `order_id`, highest `kafka_offset` wins) and `gold.orders_daily_metrics` (per `event_date`/`country`/`status`: `orders_count`, `total_amount`, `avg_amount`, `distinct_customers`). Violations are counted and logged; `QUALITY_FAIL_ON_VIOLATIONS=1` aborts the cycle instead.
- `iceberg/common/ops.py` — `Metrics.record()` writes one row to `marts.lakehouse_metrics` after each writer batch and each medallion cycle (best-effort; `METRICS_ENABLED=0` disables it). See [CONFIGURATION.md](CONFIGURATION.md).

### Iceberg maintenance DAG

`dags/lakehouse_maintenance.py` (`lakehouse_maintenance`, hourly schedule, also manually triggerable) runs the Trino Iceberg table procedures through the `iceberg` catalog:

- `ALTER TABLE <schema>.<table> EXECUTE optimize (file_size_threshold => '10MB')`
- `ALTER TABLE <schema>.<table> EXECUTE expire_snapshots (retention_threshold => '1h', retain_last => 5, clean_expired_metadata => false)`
- `ALTER TABLE <schema>.<table> EXECUTE remove_orphan_files (retention_threshold => '1h')`

Targets are `bronze.orders`, `silver.orders_clean`, `gold.orders_daily_metrics`. Airflow maps one `maintain_table` task instance per target and schedules at most one mapped instance per DagRun. Each instance runs the three procedures once in order and synchronously upserts its own before/after result to `marts.maintenance_runs`. Success is `ok`/`noop`; failure is `failed:<operation>` and the original exception is re-raised. `clean_expired_metadata=false` retains obsolete schema/spec metadata for REST compatibility but leaves snapshot/file retention active. Tuning knobs: `TRINO_HOST`/`TRINO_PORT`/`TRINO_USER`, `MAINTENANCE_RETENTION`, `MAINTENANCE_RETAIN_LAST`, `MAINTENANCE_FILE_SIZE_THRESHOLD`. The Trino catalog lowers `iceberg.expire-snapshots.min-retention`/`remove-orphan-files.min-retention` to `1h` (see [CONFIGURATION.md](CONFIGURATION.md)).

Trigger a run: `docker exec de-demo-airflow airflow dags trigger lakehouse_maintenance` (unpause first if needed).

### Operational scripts

`stack.ps1` wraps the per-command scripts in `scripts/`:

| Script | Purpose |
|---|---|
| `scripts/stack-up.ps1`, `stack-down.ps1`, `stack-build.ps1`, `stack-status.ps1`, `stack-logs.ps1`, `stack-reset.ps1` | Stack lifecycle behind `stack.ps1`. |
| `scripts/doctor.cmd` / `doctor.sh` | Environment diagnostics (Docker, Compose, CSV files, ports). |
| `scripts/show_layers.cmd` / `show_layers.sh` | Inspect `stg`/`core`/`marts` layer state. |
| `scripts/run_checks.cmd` / `run_checks.sh` | Run the SQL quality checks in `db/demo_sql/`. |
| `scripts/build_report.cmd` / `build_report.sh` | Render `reports/demo_quality_report.html`. <!-- VERIFY: reports/demo_quality_report.html is a runtime artifact generated by the script, not committed to the repo --> |
| `scripts/check_task_sql.cmd` / `check_task_sql.sh` | Grade the SQL exercise (`db/tasks/01_create_payment_type_daily.sql`). |
| `scripts/check_task_airflow.cmd` / `check_task_airflow.sh` | Grade the Airflow quality-gate exercise. |
