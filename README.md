# Local Data Engineering Platform

A Docker Compose-based local data platform for batch processing, streaming, orchestration, object storage, analytics, and interactive development.

## Architecture

```text
                                  ┌─────────────────┐
                                  │     Airflow     │
                                  │ localhost:18085 │
                                  └────────┬────────┘
                                           │
                                           ▼
┌──────────────────┐   Spark Connect   ┌───────────────────┐
│     Jupyter      │ ─────────────────▶│  Spark Connect    │
│ localhost:18888  │   sc://...:15002  │ localhost:15002   │
└────────┬─────────┘                   └─────────┬─────────┘
         │ Classic Spark                          │
         ▼                                        ▼
┌──────────────────┐                   ┌───────────────────┐
│   Spark Master   │──────────────────▶│   Spark Worker    │
│ localhost:18080  │                   │ localhost:18081   │
└────────┬─────────┘                   └───────────────────┘
         │
          ├──────────────────────────────┐
          │                              │
          ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│    PostgreSQL    │          │      MinIO       │
│ localhost:15432  │          │ API: 19000       │
└────────┬─────────┘          │ Console: 19001   │
         │                    └────────┬─────────┘
         ▼                             │
┌──────────────────┐                   ▼
│     Metabase     │          ┌──────────────────┐
│ localhost:13000  │          │   Iceberg REST   │
└──────────────────┘          │    Catalog       │
                              │ localhost:18181  │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │      Trino       │
                              │ localhost:18082  │
                              └──────────────────┘

┌──────────────────┐          ┌──────────────────┐
│      Kafka       │─────────▶│     Kafka UI     │
│ localhost:19092  │          │ localhost:18090  │
└────────┬─────────┘          └──────────────────┘
         │
         ▼
Spark Structured Streaming (Spark 4.2)
         │
         ▼
     Landing (raw Parquet in MinIO)
         │
         ▼
Iceberg writer (PyIceberg -> REST Catalog)
```

### Optional observability plane

The adopted NG-0.5 profile is opt-in. First-party traces and logs flow over
OTLP to the OpenTelemetry Collector. Traces are routed through
`telemetry-backend` to Tempo; logs remain Collector-only until NG-0.6 provides
a separately authorised log backend. Existing application Prometheus metrics
remain directly scraped by Prometheus; Grafana links bounded Prometheus
exemplars to the same Tempo trace. This profile does not replace the existing
Prometheus/Grafana path.

The complete NG-0.5 trace capability requires both `--profile otel` and
`--profile observability-next`.

## Components and URLs

| Component | Purpose | Host access |
|---|---|---|
| Airflow | Pipeline orchestration | `http://localhost:18085` |
| Spark Master UI | Cluster and application management | `http://localhost:18080` |
| Spark Worker UI | Worker status and resources | `http://localhost:18081` |
| Spark Connect | Remote Spark endpoint | `sc://localhost:15002` |
| Spark Connect UI | Connect driver UI | `http://localhost:14040` |
| JupyterLab | Interactive PySpark development | `http://localhost:18888` |
| PostgreSQL | Data warehouse | `localhost:15432` |
| MinIO API | S3-compatible endpoint | `http://localhost:19000` |
| MinIO Console | Object storage UI | `http://localhost:19001` |
| Iceberg REST Catalog | Iceberg metadata catalog and warehouse manager | `http://localhost:18181` |
| Iceberg writer | PyIceberg job: staging Parquet -> Iceberg bronze tables | (internal) |
| Trino | SQL engine over Iceberg (REST catalog) | `http://localhost:18082` |
| Kafka | Event-streaming broker | `localhost:19092` |
| Kafka UI | Kafka administration | `http://localhost:18090` |
| Metabase | Analytics and dashboards | `http://localhost:13000` |
| Prometheus | Directly scraped application metrics | `http://localhost:19090` |
| Grafana | Prometheus/Tempo correlation UI (Tempo backend is optional) | `http://localhost:13001` |
| OpenTelemetry Collector | OTLP receiver and bounded telemetry queue | internal only (`otel-collector:13133` health) |
| Tempo | Trace query API (optional profile) | `http://localhost:13200` |

## Requirements

- Windows 10 or Windows 11
- Docker Desktop using Linux containers
- `uv` 0.12.5
- WSL2 backend
- PowerShell 5.1 or PowerShell 7
- At least 12 GB RAM available to Docker; 16 GB is preferable

Install the exact project uv version on Windows, then verify it before setup:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.12.5/install.ps1 | iex"
uv --version  # must report uv 0.12.5
```

## Initial setup

Create the runtime environment file:

```powershell
Copy-Item .env.example .env
```

Replace the placeholder values for `AIRFLOW_API_SECRET_KEY`,
`AIRFLOW_JWT_SECRET`, and `AIRFLOW_DB_PASSWORD` with three independent random
URL-safe secrets. The extended stack also requires a real
`SUPERSET_SECRET_KEY`. The optional observability profile additionally needs
`TEMPO_S3_SECRET_KEY` and `GRAFANA_ADMIN_PASSWORD` set to non-placeholder
values.

Validate Compose:

```powershell
docker compose `
  --env-file .\.env `
  -f .\docker-compose.yml `
  -f .\docker-compose.extended.yml `
  config
```

Build and start:

```powershell
.\stack.ps1 build
.\stack.ps1 up
.\stack.ps1 status
```

## Commands

```powershell
.\stack.ps1 up
.\stack.ps1 down
.\stack.ps1 build
.\stack.ps1 build -NoCache
.\stack.ps1 build -Service jupyter
.\stack.ps1 status
.\stack.ps1 logs
.\stack.ps1 logs -Service kafka
.\stack.ps1 logs -Service spark-worker -Tail 500
.\stack.ps1 logs -Service spark-worker -NoFollow
```

## Jupyter authentication

```powershell
docker exec de-demo-jupyter jupyter server list
```

Replace container port `8888` with host port `18888` in the returned URL.

## PostgreSQL

Host connection:

```text
Host: localhost
Port: 15432
Database: dwh
Username: value from POSTGRES_USER
Password: value from POSTGRES_PASSWORD
```

Container connection:

```text
de-demo-postgres:5432
```

## MinIO

Console: `http://localhost:19001`

Internal S3 endpoint: `http://minio:9000`

## Iceberg

The lakehouse uses an Iceberg REST catalog backed by MinIO:

- REST catalog: `http://localhost:18181` (`iceberg-rest` service, SQLite metadata in the `de_demo_iceberg_catalog` volume)
- Warehouse: `s3://de-practicum/warehouse`
- Writer: `iceberg-writer` service runs `iceberg/writer/iceberg_writer.py`, which polls the landing bucket (`s3://de-practicum/streaming/orders_raw`) and appends new Parquet files into `bronze.orders` via PyIceberg. Ingested file paths are tracked in the `de_demo_iceberg_writer_state` volume.
- Medallion: `iceberg-medallion` service runs `iceberg/medallion/iceberg_medallion.py`, which rebuilds `silver.orders_clean` (deduplicated by `order_id`, highest `business_version` wins) and `gold.orders_daily_metrics` (per-day, per-country, per-status aggregates) from bronze every 60 seconds.
- Metrics: the writer contributes a single observability row per batch and the medallion contributes a row per phase plus a `cycle` envelope row to `marts.lakehouse_metrics` in PostgreSQL (see *Observability metrics* below).
- Maintenance: the Airflow DAG `lakehouse_maintenance` runs snapshot expiry, orphan-file cleanup, and compaction through Trino (see *Iceberg maintenance* below).
- Trino: `http://localhost:18082` with the `iceberg` catalog. `trino/etc/catalog/iceberg.properties` is generated at container startup from `iceberg.properties.template` using `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (see `trino/etc/start-trino.sh`), so credentials are never hardcoded in the repo.

### Naming: landing vs bronze vs silver vs gold

- **Landing** (`s3://de-practicum/streaming/orders_raw`): raw Parquet as written by Spark Structured Streaming. Uncurated, may contain duplicates if the stream replays.
- **Bronze** (`bronze.orders`): raw rows ingested 1:1 from landing. Partitioned by `event_date`, one snapshot per ingestion batch.
- **Silver** (`silver.orders_clean`): deduplicated orders — one row per `order_id` (the row with the highest `business_version` wins). Kafka transport order never decides which observation is current, and equal versions with conflicting payloads are rejected before any write (FF-14). The executable contract is `tests/features/silver_business_state.feature`.
- **Gold** (`gold.orders_daily_metrics`): business-ready aggregates grouped by `event_date`, `country`, `status`.

### Idempotency and crash recovery

The writer is at-least-once: each batch is committed with a `load-id` in the snapshot summary, and the state file keeps both `done` (acknowledged files) and `pending` (files recorded but not yet acknowledged) entries. On restart it re-checks `pending` load-ids against the table's snapshot summaries:

- load-id already committed → the files are marked done, **no re-append** (no duplicates);
- load-id missing → the append never committed, so the files are re-appended.

To demo recovery, crash the writer right after a commit:

```powershell
$c = "docker compose -f docker-compose.yml -f docker-compose.extended.yml"
& $c stop iceberg-writer
& $c run --rm -e SIMULATE_CRASH_AFTER_COMMIT=1 iceberg-writer
& $c start iceberg-writer
```

The crash run exits right after committing (leaving a `pending` entry in the state volume), and `start` recovers it — the log line `Recovery: load <id> already committed ... -> marked done, no re-append` confirms the rows were **not** appended a second time.

> **Snapshot frequency.** The demo commits a snapshot roughly every 10 seconds so the Iceberg snapshot log grows visibly and time travel stays easy to demonstrate. Production streaming jobs would batch commits (e.g. on a time/row-count watermark) and run regular compaction plus snapshot expiration to keep the metadata log small; the `load-id` mechanism above works the same way regardless of commit frequency.

> **Why PyIceberg instead of Spark?** Iceberg 1.11 has no `iceberg-spark-runtime-4.2` JAR (Maven Central, Apache snapshots, and the Iceberg main branch only cover up to Spark 4.1). Spark 4.2 also changed `View` from an interface to a class, so a 4.2 runtime cannot be a trivial recompile. The pipeline therefore keeps Spark 4.2 for streaming, writes raw Parquet to the landing bucket, and ingests into Iceberg with PyIceberg. Once Iceberg ships a 4.2 runtime, the writer can be replaced by a direct Spark sink without touching the catalog, warehouse, or Trino.

### Quality checks (bronze → silver)

Each medallion cycle runs data-quality assertions on the bronze batch with PyArrow (`iceberg/medallion/iceberg_medallion.py` → `run_quality_checks`):

- `order_id` is not null;
- `amount` is not null and greater than zero;
- `country` is not null;
- `status` is in the allowed set `created, paid, shipped, delivered`;
- `event_time` is not null.

Violation counts are logged and written to `marts.lakehouse_metrics.quality_violations`. Processing continues by default; set `QUALITY_FAIL_ON_VIOLATIONS=1` on the `iceberg-medallion` service to abort the cycle when any check fails. Allowed statuses are configurable via `QUALITY_VALID_STATUSES` (comma-separated).

### Observability metrics

Each writer batch inserts a single row into `marts.lakehouse_metrics` (schema auto-created, best-effort). A medallion **cycle** inserts several: one row for each phase it executed, plus a `cycle` row written last. Every row of one cycle carries the same `cycle_id`, and `phase` says which kind of row it is — the closed set is `b2`, `shadow`, `gold` and `cycle`.

The `cycle` row is the envelope, and `silver_duration_ms` / `gold_duration_ms` keep their inclusive meaning there. Phase durations are mutually non-overlapping, but they sum to *at most* the cycle duration rather than exactly to it: the incremental writer's own state-load preamble — loading progress, listing the outbox, reading the completion ledger — runs before `run_b2` starts its timer and is deliberately attributed to no phase.

| Column | Meaning |
|---|---|
| `metric_ts` | Timestamp of the batch/cycle |
| `source` | `writer` or `medallion` |
| `load_id` | Writer batch id |
| `status` | `success` or `error` |
| `rows_processed` / `files_processed` | Writer rows and files in the batch |
| `bronze_rows` / `silver_rows` / `gold_rows` | Row counts seen by the medallion cycle |
| `duplicates_removed` | `bronze_rows - silver_rows` |
| `quality_violations` | Total violations from the quality checks |
| `duration_ms` | Cycle/batch duration |
| `files_planned` / `bytes_planned` | Physical files and bytes selected by the B2 affected-key scan |
| `files_removed` / `files_added` | Data files replaced by the committed B2 overwrite |
| `bytes_removed` / `bytes_added` | Bytes replaced by the committed B2 overwrite |
| `snapshot_delta` | Silver snapshots committed by the B2 cycle |
| `cycle_id` | Identifier shared by every row of one medallion cycle; `NULL` on rows written before this phase |
| `phase` | Which row this is: `b2`, `shadow`, `gold` or `cycle` |
| `bronze_snapshot_id` | Bronze snapshot the cycle read (the pinned boundary when one was pinned) |
| `silver_snapshot_id` | Persisted Silver snapshot the cycle produced or read |
| `gold_snapshot_id` | Gold snapshot after the cycle, whether it was rewritten or left in place |
| `shadow_skipped` | Shadow comparison was enabled but a durable certificate already covered this state |
| `gold_skipped` | Gold was left in place because its provenance already names the current persisted Silver snapshot |

Disable with `METRICS_ENABLED=0`. Query the table from PostgreSQL (`localhost:15432`, database `dwh`) or build dashboards in Metabase or Superset:

```sql
select source, status, count(*), round(avg(duration_ms)) as avg_ms
from marts.lakehouse_metrics
where phase = 'cycle' or phase is null
group by 1, 2
order by 1, 2;
```

The `where` clause is what keeps the numbers honest: without it a single medallion cycle is counted two to four times, once per phase row. `phase is null` keeps the rows written before this phase, which have no phase to filter on.

#### Reading rows written before this phase

Rows with `cycle_id IS NULL` predate phase separation and have to be inferred, because `run_b2` and the outer cycle both wrote `source="medallion"` and the outer `silver_duration_ms` already contained the nested B2 duration. The rule is **status-qualified**:

| `status` | `gold_duration_ms` | Classified as | What the row is |
|---|---|---|---|
| `success` | `> 0` | `cycle` | an outer cycle |
| `success` | `0` | `b2` | a nested B2 phase |
| `shadow_failed` | never set | `cycle` | an outer cycle that aborted before Gold |
| `failed` | any | `nested` | a nested phase for which no outer record exists |

The naive form of this rule — "`gold_duration_ms = 0` means a nested phase" — misclassifies `shadow_failed`, which is the safety-critical row: the cycle raises before Gold runs, so that field is never set, yet the row describes an outer cycle that aborted, not a nested phase.

A `failed` row is classified `nested` rather than `b2` deliberately. It may come from the incremental write or from an aborted legacy cycle under `QUALITY_FAIL_ON_VIOLATIONS=1`, and nothing in the row distinguishes the two; what both origins share is that no outer record exists for that cycle. `classify_metric_row` in `iceberg/common/ops.py` is the executable form of this table — use it rather than re-deriving the rule, so prose and code cannot drift apart.

**Provenance of the rule, stated plainly:** the two `success` branches are grounded in recorded data, but the `shadow_failed` and `failed` branches were **derived by reading the emission sites in `iceberg/medallion/iceberg_medallion.py`, not observed in recorded data** — every one of the ten rows in `artifacts/b2-rollout/06-o1-window.json` has `status: success`.

#### Work the cycle can skip

Both skips are memoisation, never a partial result, and every failure to establish the fact results in doing the full work:

- **Gold** is rebuilt in full whenever persisted Silver moves, and left in place when the current Gold snapshot's `source-silver-snapshot-id` already names the current persisted Silver snapshot. An absent, unparsable or superseded provenance rebuilds. A Trino maintenance rewrite of Gold (`optimize`, `expire_snapshots`) drops that property, which deliberately costs exactly one extra rebuild. See the D-4 amendment in [ADR-0001](docs/adr/0001-incremental-silver-and-gold.md).
- **The shadow comparison** is skipped when a durable certificate covers the current Bronze snapshot, the current persisted Silver snapshot, the runtime identity and the projection contract. The certified pair is re-checked after the incremental writer runs, because both can move mid-cycle; if they have, the cycle either performs the real comparison or, when the fast path had already skipped the Bronze pin, fails closed before Gold and publishes nothing.

At a 60 second interval the medallion now writes roughly two to four rows per cycle where it previously wrote two, so recorded growth of about 970 rows/day scales accordingly. Retention for this table was not decided in this phase.

### Iceberg maintenance

PyIceberg 0.11.1 cannot expire snapshots or delete orphan files, so maintenance runs through **Trino 483** table procedures (`ALTER TABLE ... EXECUTE ...`), which operate directly on the warehouse via Trino's file IO:

- `expire_snapshots(retention_threshold => '1h', retain_last => 5, clean_expired_metadata => false)`
- `remove_orphan_files(retention_threshold => '1h')`
- `optimize(file_size_threshold => '10MB')` (compaction)

The explicit `clean_expired_metadata=false` setting retains obsolete schema and
partition-spec definitions for compatibility with the persisted Iceberg REST
catalog; snapshot expiry, expired-file cleanup, `retain_last=5`, and the
existing retention threshold still run. The catalog template lowers the
built-in safety floor for these procedures to `1h`
(`iceberg.expire-snapshots.min-retention`,
`iceberg.remove-orphan-files.min-retention`), so the demo can actually
demonstrate expiry instead of no-op.

The Airflow DAG `lakehouse_maintenance` (`dags/lakehouse_maintenance.py`) runs
all three procedures on `bronze.orders`, `silver.orders_clean`, and
`gold.orders_daily_metrics` hourly (and on manual trigger). Airflow allows one
DagRun and one mapped table instance at a time. Each mapped instance commits
its own before/after result to `marts.maintenance_runs`; failures are recorded
as `failed:<operation>` and re-raised so the task and DagRun remain failed. The
Iceberg writer retries its own commit conflicts (`CommitFailedException`), but
maintenance procedures are never retried.

The warehouse batch is split across two single-active-run DAGs in
`dags/warehouse_orders.py`. Manually trigger `warehouse_orders_ingestion`; it
loads and validates staging, runs the unchanged core rebuild SQL, and performs
a read-only core query/count readiness check. Only its terminal
`core.publish_core_assets` task emits `core.orders` and `core.order_items`
events, with integer `row_count` metadata. A failed or partial ingestion emits
no scheduling event. The successful `core.orders` event automatically starts
`warehouse_marts_validation`, which validates the existing marts views, runs
the unchanged payment reconciliation, publishes mart Assets, and writes the
audit. `marts.pipeline_runs.run_id` remains the downstream DagRun primary key;
nullable `ingestion_run_id` records the native Asset event source DagRun.

Run the exact one-shot proof only against a healthy stack:

```powershell
uv run --locked python scripts/verify_warehouse_asset_flow.py
```

The verifier triggers ingestion once and never triggers the downstream DAG
directly. Its JSON receipt proves the source run, Asset events, automatic
consumer run, and audit provenance.

```powershell
# run maintenance now
docker exec de-demo-airflow airflow dags trigger lakehouse_maintenance

# watch the snapshot log shrink
docker exec de-demo-trino trino --execute "SELECT count(*) FROM iceberg.bronze.orders"
docker exec de-demo-postgres psql -U app -d dwh -c "SELECT * FROM marts.maintenance_runs"
```

For a fail-closed live check, run `uv run --locked python
scripts/verify_maintenance_dag.py`. The verifier generates one unique
`maintenance_verify_...` run ID, triggers it once, and accepts only that exact
successful DagRun with exactly one `ok`/`noop` audit row for every configured
target; it does not use a time lookback.

Query Iceberg from Trino:

```powershell
docker exec de-demo-trino trino --execute "SELECT count(*) FROM iceberg.bronze.orders"
docker exec de-demo-trino trino --execute "SELECT count(*) FROM iceberg.silver.orders_clean"
docker exec de-demo-trino trino --execute "SELECT event_date, country, status, orders_count, total_amount FROM iceberg.gold.orders_daily_metrics LIMIT 10"
```

Time travel (version and timestamp based):

```sql
SELECT count(*) FROM iceberg.bronze.orders FOR VERSION AS OF 2540098444538675289;
SELECT count(*) FROM iceberg.bronze.orders FOR TIMESTAMP AS OF TIMESTAMP '2026-08-07 16:11:00 UTC';
```

## Kafka

Kafka UI: `http://localhost:18090`

Internal bootstrap server: `kafka:9092`

Create the `orders` topic:

```powershell
docker exec de-demo-kafka `
  /opt/kafka/bin/kafka-topics.sh `
  --bootstrap-server kafka:9092 `
  --create `
  --if-not-exists `
  --topic orders `
  --partitions 3 `
  --replication-factor 1
```

## Spark modes

Classic mode:

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .appName("classic-session")
    .master("spark://spark-master:7077")
    .config("spark.pyspark.python", "/usr/bin/python3")
    .getOrCreate()
)
```

Spark Connect:

```python
from pyspark.sql import SparkSession

spark = (
    SparkSession.builder
    .remote("sc://spark-connect:15002")
    .appName("connect-session")
    .getOrCreate()
)
```

Classic Spark and Spark Connect can compete for the same local worker. Stop unused applications when resources are exhausted.

## Health checks

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}"
docker inspect de-demo-kafka --format "{{json .State.Health}}"
docker inspect de-demo-spark-connect --format "{{json .State.Health}}"
```

## Safe stop versus destructive reset

Safe stop keeps persistent volumes:

```powershell
.\stack.ps1 down
```

> **Warning:** reset removes named Docker volumes and may delete PostgreSQL data, MinIO objects, Metabase configuration, and other persisted local state.

Interactive reset:

```powershell
.\stack.ps1 reset
```

Type `RESET` when prompted.

Non-interactive reset:

```powershell
.\stack.ps1 reset -Force
```

## Troubleshooting

No Spark resources: open `http://localhost:18080` and stop old applications.

Jupyter token rejected:

```powershell
docker exec de-demo-jupyter jupyter server list
```

Kafka logs:

```powershell
.\stack.ps1 logs -Service kafka
```

Validate after Compose edits:

```powershell
docker compose `
  --env-file .\.env `
  -f .\docker-compose.yml `
  -f .\docker-compose.extended.yml `
  config --services
```

## License

This repository does not include a `LICENSE` file. No license is granted unless one is added.
