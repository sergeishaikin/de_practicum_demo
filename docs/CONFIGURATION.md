<!-- generated-by: gsd-doc-writer -->
# Configuration

## Environment variables

### Base variables (`.env`, from `.env.example`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `COMPOSE_PROJECT_NAME` | Optional | `de-practicum-demo` | Compose project name. |
| `POSTGRES_IMAGE` | Optional | `postgres:15` | Postgres image tag. |
| `POSTGRES_USER` | Optional | `app` | Postgres superuser for the demo DB. |
| `POSTGRES_PASSWORD` | Optional | `change-me` | Postgres password. |
| `POSTGRES_DB` | Optional | `dwh` | Demo database name. |
| `POSTGRES_HOST_PORT` | Optional | `15432` | Host port for Postgres. |
| `AIRFLOW_DB_NAME` | Optional | `airflow_meta` | Dedicated Airflow metadata database in the shared PostgreSQL instance. |
| `AIRFLOW_DB_USER` | Optional | `airflow` | Dedicated Airflow metadata role. |
| `AIRFLOW_DB_PASSWORD` | Required | none | URL-safe password for the Airflow metadata role. |
| `AIRFLOW_HOST_PORT` | Optional | `18085` | Loopback-only host port for the Airflow API server and UI. |
| `AIRFLOW_API_SECRET_KEY` | Required | none | Secret used by the Airflow API server. |
| `AIRFLOW_JWT_SECRET` | Required | none | Shared JWT signing secret for Airflow components. |
| `SPARK_MASTER_UI_PORT` | Optional | `18080` | Spark Master UI port. |
| `SPARK_WORKER_UI_PORT` | Optional | `18081` | Spark Worker UI port. |
| `SPARK_MASTER_PORT` | Optional | `17077` | Spark Master RPC port. |
| `SPARK_CONNECT_PORT` | Optional | `15002` | Spark Connect gRPC port. |
| `SPARK_CONNECT_UI_PORT` | Optional | `14040` | Spark Connect driver UI port. |
| `JUPYTER_HOST_PORT` | Optional | `18888` | Jupyter host port. |
| `MINIO_IMAGE` | Optional | `minio/minio:RELEASE.2025-04-22T22-12-26Z` | MinIO image tag. |
| `MINIO_ROOT_USER` | Optional | `minio` | MinIO access key (root user). |
| `MINIO_ROOT_PASSWORD` | Optional | `change-me` | MinIO secret key (root password). |
| `MINIO_API_PORT` | Optional | `19000` | MinIO S3 API host port. |
| `MINIO_CONSOLE_PORT` | Optional | `19001` | MinIO console host port. |
| `METABASE_IMAGE` | Optional | `metabase/metabase:v0.54.6` | Metabase image tag. |
| `METABASE_HOST_PORT` | Optional | `13000` | Metabase host port. |
| `KAFKA_IMAGE` | Optional | `apache/kafka:4.0.0` | Kafka image tag. |
| `KAFKA_HOST_PORT` | Optional | `19092` | Kafka host port. |
| `KAFKA_UI_IMAGE` | Optional | `provectuslabs/kafka-ui:latest` | Kafka UI image tag. |
| `KAFKA_UI_HOST_PORT` | Optional | `18090` | Kafka UI host port. |
| `ICEBERG_REST_IMAGE` | Optional | `tabulario/iceberg-rest:latest` | Iceberg REST catalog image tag. |
| `ICEBERG_REST_PORT` | Optional | `18181` | Iceberg REST catalog host port. |
| `TRINO_IMAGE` | Optional | `trinodb/trino:483` | Trino image tag. |
| `TRINO_HOST_PORT` | Optional | `18082` | Trino host port. |
| `PROMETHEUS_IMAGE` | Optional | `prom/prometheus:v3.5.0` | Prometheus image tag. |
| `PROMETHEUS_HOST_PORT` | Optional | `19090` | Prometheus host port. |
| `GRAFANA_IMAGE` | Optional | `grafana/grafana:11.2.0` | Grafana image tag. |
| `GRAFANA_HOST_PORT` | Optional | `13001` | Grafana host port. |

### Required beyond `.env.example`

| Variable | Required | Description |
|---|---|---|
| `SUPERSET_SECRET_KEY` | **Required for Superset** | Used by `superset` and `superset-mcp`; referenced in `docker-compose.extended.yml` without a default and read by `superset/superset_config.py`. Add it to `.env` or the services fail to start. |

### Component-level variables (set in Compose files, with code defaults)

These are configured in `docker-compose.extended.yml`; the values below are the defaults used by the code when the variable is absent.

Iceberg writer (`iceberg/writer/iceberg_writer.py`):

| Variable | Default | Description |
|---|---|---|
| `ICEBERG_CATALOG_URI` | `http://iceberg-rest:8181` | REST catalog URL. |
| `ICEBERG_WAREHOUSE` | `s3://de-practicum/warehouse` | Warehouse root. |
| `ICEBERG_NAMESPACE` | `bronze` | Target namespace. |
| `ICEBERG_TABLE` | `orders` | Target table. |
| `MINIO_BUCKET` | `de-practicum` | Bucket with the landing data. |
| `LANDING_PREFIX` | `streaming/orders_raw` | Prefix polled for new Parquet files. |
| `POLL_INTERVAL_SECONDS` | `10` | Polling interval. |
| `STATE_FILE` | `/state/ingested.json` | Persisted ingestion state. |
| `MAX_APPEND_ATTEMPTS` | `5` | How many times to retry a commit that fails with `CommitFailedException` (conflict with a concurrent writer or maintenance). |
| `SIMULATE_CRASH_AFTER_COMMIT` / `SIMULATE_CRASH_BEFORE_COMMIT` | `0` | Demo switches that force a simulated crash (`1` enables). |
| `PROMETHEUS_METRICS_PORT` | unset locally; `9101` in Compose | In-process metrics HTTP port. |

Iceberg medallion (`iceberg/medallion/iceberg_medallion.py`): `BRONZE_NAMESPACE`/`BRONZE_TABLE` (defaults `bronze`/`orders`), `SILVER_NAMESPACE`/`SILVER_TABLE` (defaults `silver`/`orders_clean`), `GOLD_NAMESPACE`/`GOLD_TABLE` (defaults `gold`/`orders_daily_metrics`), `MEDALLION_INTERVAL_SECONDS` (default `60`), `QUALITY_VALID_STATUSES` (default `created,paid,shipped,delivered`, comma-separated allowed `status` values), `QUALITY_FAIL_ON_VIOLATIONS` (default `0`; `1` aborts the cycle when a quality check fails), `PROMETHEUS_METRICS_PORT` (unset locally; `9102` in Compose), plus the shared `ICEBERG_CATALOG_URI`, `ICEBERG_WAREHOUSE`, `S3_ENDPOINT`, `S3_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

Metrics (`iceberg/common/ops.py`, used by writer and medallion): `METRICS_ENABLED` (default `1`; `0` disables metric writes), `POSTGRES_HOST` (`de-demo-postgres`), `POSTGRES_PORT` (`5432`), `POSTGRES_DB` (`dwh`), `POSTGRES_USER` (`app`), `POSTGRES_PASSWORD` (`app`). Metric writes are best-effort: a Postgres failure is logged and never breaks ingestion.

Orders streaming (`spark/jobs/orders_streaming.py`): `KAFKA_BOOTSTRAP_SERVERS` (`kafka:9092`), `KAFKA_TOPIC` (`orders`), `KAFKA_FAIL_ON_DATA_LOSS` (`true`, stop loudly when Kafka offsets are unavailable), optional `KAFKA_MAX_OFFSETS_PER_TRIGGER` and `STREAMING_TRIGGER_SECONDS` throttles, `PROMETHEUS_METRICS_PORT` (`9103` in Compose), `MINIO_BUCKET` (`de-practicum`), `RAW_OUTPUT_PATH` (`s3a://de-practicum/streaming/orders_raw`), `RAW_CHECKPOINT_PATH`, `POSTGRES_CHECKPOINT_PATH`, `DEAD_LETTER_OUTPUT_PATH`, `DEAD_LETTER_CHECKPOINT_PATH`, `RECONCILIATION_OUTPUT_PATH`, `RECONCILIATION_CHECKPOINT_PATH`, and `POSTGRES_HOST`/`PORT`/`DB`/`USER`/`PASSWORD` (defaults `de-demo-postgres`/`5432`/`dwh`/`app`/`app`). Invalid JSON or records without `order_id` are retained under the dead-letter prefix with the raw payload and Kafka metadata. Each micro-batch also writes an idempotent disposition receipt with observed, valid, and dead-letter counts plus Kafka partition/offset bounds for source-window reconciliation.

Orders producer (`kafka/producer/orders_producer.py`): `KAFKA_BOOTSTRAP_SERVERS` (`kafka:9092`), `KAFKA_TOPIC` (`orders`), `EVENTS_PER_SECOND` (`2`).

Airflow (`docker-compose.yml`): Airflow 3.3.1 runs through `airflow standalone` with `LocalExecutor` (parallelism `4`), PostgreSQL metadata, and Simple Auth Manager's local-only all-admin mode. The UI is named `DE Practicum · Local`, its port is bound to `127.0.0.1`, and there is no login prompt. `AIRFLOW_API_SECRET_KEY`, `AIRFLOW_JWT_SECRET`, and `AIRFLOW_DB_PASSWORD` are distinct required values. DAG connections use `DWH_HOST`, `DWH_PORT`, `DWH_DB`, `DWH_USER`, and `DWH_PASSWORD`, while `TZ` defaults to `Europe/Moscow`.

Existing checkouts must refresh `.env`: remove the Airflow 2 keys
`AIRFLOW_SECRET_KEY` and `AIRFLOW_ADMIN_PASSWORD`, then add independent random
values for `AIRFLOW_API_SECRET_KEY` and `AIRFLOW_JWT_SECRET`.

Also add a third independent, URL-safe value for `AIRFLOW_DB_PASSWORD`.
`AIRFLOW_DB_NAME` and `AIRFLOW_DB_USER` normally keep their defaults. The
idempotent `airflow-db-init` service creates or refreshes that role and database
before Airflow starts, including when the PostgreSQL volume already exists.

Airflow metadata is stored in the dedicated `airflow_meta` PostgreSQL database
inside the existing persistent Postgres volume. Recreating the Airflow
container therefore preserves DAG run history, variables, and other metadata.

Iceberg maintenance DAG (`dags/lakehouse_maintenance.py`): `TRINO_HOST` (`trino`), `TRINO_PORT` (`8080`), `TRINO_USER` (`admin`), `MAINTENANCE_RETENTION` (`2h`, retention threshold passed to `expire_snapshots`/`remove_orphan_files`), `MAINTENANCE_RECOVERY_HORIZON` (`1h`, maximum writer recovery period), `MAINTENANCE_RECOVERY_SAFETY_MARGIN` (`15m`, import-time validation requires retention to be strictly greater than horizon plus margin), `MAINTENANCE_RETAIN_LAST` (`5`, snapshots always kept by `expire_snapshots`), `MAINTENANCE_FILE_SIZE_THRESHOLD` (`10MB`, passed to `optimize`). The DAG runs hourly (`schedule="0 * * * *"`), allows one active run, and is also manually triggerable. Each hardcoded target (`bronze.orders`, `silver.orders_clean`, `gold.orders_daily_metrics`) becomes a separately visible mapped task instance; Airflow schedules at most one such instance per DagRun and the three non-retried maintenance procedures remain sequential inside it. Snapshot expiry explicitly uses `clean_expired_metadata=false`: obsolete schema/spec definitions remain, while the existing snapshot/file retention, recovery horizon, and `retain_last` contracts are unchanged. Each mapped task commits its own audit result, including `failed:<operation>` before re-raising failures.

The manual batch DAG `demo_core_marts_pipeline` also allows one active run. Its
`validate_staging` task has the four fixed staging Assets as inlets and requires
exact, non-empty CSV/staging row-count parity before core or marts SQL runs.

## Config file format

The primary configuration is Docker Compose YAML:

- `docker-compose.yml` — base stack: `de-demo-postgres`, the one-shot `airflow-db-init`, and `de-demo-airflow`.
- `docker-compose.extended.yml` — the extended stack: MinIO, Spark, Jupyter, Kafka, Iceberg, Trino, Superset, Metabase, and the producer/streaming services. References the shared network and adds named volumes.
- `docker-compose.local-airflow.yml` — offline fallback for the base stack using a pre-built local image (`local/airflow:3.3.1-lab`, `pull_policy: never`).

Runtime config files:

- `trino/etc/catalog/iceberg.properties.template` — Trino Iceberg catalog template. `trino/etc/start-trino.sh` substitutes `TRINO_S3_ACCESS_KEY` / `TRINO_S3_SECRET_KEY` into `trino/etc/catalog/iceberg.properties` at container start, so credentials are never hardcoded. The template also lowers the maintenance safety floor: `iceberg.expire-snapshots.min-retention=1h` and `iceberg.remove-orphan-files.min-retention=1h` (defaults are 7 days) so the demo can expire snapshots younger than a week.
- `trino/etc/config.properties`, `trino/etc/jvm.config`, `trino/etc/node.properties` — Trino server settings.
- `superset/superset_config.py` — Superset Python config (reads `SUPERSET_SECRET_KEY`; local MCP settings).

Copy `.env.example` for the base stack, then replace its secret placeholders.
`.env.extended.example` is an alternate minimal template for the extended
stack and likewise requires real secret values.

## Required vs optional settings

- Missing `SUPERSET_SECRET_KEY` fails Superset startup (`superset/superset_config.py` raises `KeyError`). Required only if you run the Superset services.
- Missing `AIRFLOW_DB_PASSWORD`, `AIRFLOW_API_SECRET_KEY`, or
  `AIRFLOW_JWT_SECRET` fails Compose interpolation for the Airflow service.
- `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` are used by MinIO itself and injected into every S3-dependent service (Spark, Iceberg, Trino). Keep them consistent; the values can be changed in `.env`, but restart MinIO and dependent services afterwards.
- Every other base variable has a value in `.env.example` or a Compose interpolation default, so an unset variable only changes the port/image rather than breaking startup.

## Defaults

Defaults live in two places:

- `.env.example` — the reference set used to generate `.env` (ports and image tags).
- Code-level defaults in `iceberg/writer/iceberg_writer.py`, `iceberg/medallion/iceberg_medallion.py`, `iceberg/common/ops.py`, `spark/jobs/orders_streaming.py`, `kafka/producer/orders_producer.py`, and `dags/lakehouse_maintenance.py`, applied via `os.getenv("NAME", "default")` when a variable is absent from the environment.

## Per-environment overrides

- Different hosts can use different `.env` files; scripts always pass `--env-file .env` explicitly.
- `docker-compose.local-airflow.yml` provides an offline/development variant of the base stack.
- There are no `.env.development` / `.env.production` files; environment-specific values are handled by editing `.env` (or providing an alternate env file to Compose).
- `TZ` defaults to `Europe/Moscow` in `docker-compose.yml`; override it in `.env` to change the demo timezone across Airflow and Postgres.
