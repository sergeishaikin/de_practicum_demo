---
gsd_findings_version: 1.0
task: docker-storage-investigation
mode: quick
created: 2026-08-16
status: investigation-complete-no-deletion
---

# Docker storage investigation — findings

Investigation only. **Nothing was deleted as part of this task.** Removal is
staged below and awaits authorization.

Prior context: under separate approval earlier the same day,
`docker builder prune -af` (15.94 GB) and `docker image prune -a -f` (3.95 GB)
were already run. Both categories are therefore near-empty here and are not a
remaining source of reclaimable space.

## 1. The headline number is an accounting artifact

`docker system df` reports:

| Type | Total | Active | Size | Reclaimable |
|---|---|---|---|---|
| Images | 22 | 20 | 996.2 GB | 356.5 MB (0%) |
| Containers | 27 | 20 | 966.2 GB | 2.245 MB (0%) |
| Local Volumes | 26 | 16 | 28.08 GB | 24.87 GB (88%) |
| Build Cache | 0 | 0 | 0 B | 0 B |

"996 GB of images" is not real. The per-container breakdown shows
`de-demo-spark-worker` at **965 GB writable / 967 GB virtual**, and the Images
row double-counts container writable layers.

**Actual unique image storage ≈ 996.2 − 966.2 ≈ 30 GB**, spread over 22 images
whose individual virtual sizes are 0.15–3.5 GB. Images are not the problem and
do not need pruning.

## 2. Where the space actually is

| Consumer | Size | Share |
|---|---|---|
| `de-demo-spark-worker` → `/opt/spark/work` | **900 GB** | ~90% of the VM disk |
| Real image layers | ~30 GB | 3% |
| Orphan volume `b420157…` | 22.5 GB | 2% |
| All project data volumes combined | ~4.3 GB | <1% |
| `de_demo_pg_data` (the warehouse itself) | 138 MB | 0.01% |

`/opt/spark/work` holds **681 application directories** at ~1.4 GB each. It is
on the container writable layer — no volume, no size bound.

### Root cause: a self-reinforcing loop

1. `spark/submit-with-runtime.sh:10` passes every jar under `/opt/spark/h1-jars`
   via `--jars` — 678 MB, of which `bundle-2.29.52.jar` (AWS SDK v2 fat bundle)
   is 612 MB. Spark stages the whole set into a fresh
   `/opt/spark/work/app-*/<executor>/` directory **on every submission**.
2. `orders-streaming` carries `restart: unless-stopped`
   (`docker-compose.extended.yml:565`) and is failing, so it resubmits every
   ~22 seconds. App IDs run `app-…-0000` → `app-…-1339` inside ~24 hours.
3. `spark-worker` sets no `SPARK_WORKER_OPTS`, so `spark.worker.cleanup.enabled`
   is off and nothing ever reclaims those directories.
4. The disk fills, and the job then fails *because of it* —
   `java.io.IOException: Failed to create a temp directory (under /tmp) after 10 attempts!`
   — which makes it fail faster and resubmit sooner.

Measured burn rate: **~1.4 GB / 22 s ≈ 230 GB per hour.**

Collateral: `de-demo-postgres` is in a crash loop with
`PANIC: could not write to file "pg_logical/replorigin_checkpoint.tmp": No space left on device`.
About 20 GB freed earlier lasted roughly 15 minutes.

Neither compose file sets a `logging:` block, so json-file container logs are
also unbounded. Secondary today, but the same class of defect.

## 3. A time-based retention policy does not address this

`find /opt/spark/work -maxdepth 1 -type d -mtime +3` returns **0 directories**.
All 681 were created within the last 24 hours. A 3-day retention job would free
zero bytes and the disk would refill in about 4 hours.

The useful horizon for Spark scratch is **hours**, and the durable fix is
configuration, not a scheduled cleanup.

## 4. Classification

### REQUIRED — protect, not reproducible

| Volume | Size | Why |
|---|---|---|
| `de_demo_pg_data` | 138.4 MB | `dwh` + `airflow_meta`: stg/core/marts, `marts.pipeline_runs` (8 rows) |
| `de-practicum-demo_de_demo_minio_data` | 1.501 GB | landing Parquet + all Iceberg data and metadata |
| `de_demo_kafka_data` | 1.153 GB | Kafka log dirs; offsets matter given the recorded fail-closed state |
| `de-practicum-demo_de_demo_iceberg_writer_state` | 1.367 MB | `/state/ingested.json` — the writer's `done`/`pending` load-ids |
| `de-practicum-demo_de_demo_superset_home` | 326.7 MB | Superset metadata and dashboards |
| `de-practicum-demo_de_demo_metabase_data` | 5.525 MB | Metabase dashboards |
| `de-practicum-demo_de_demo_prometheus_data` | 5.226 MB | metrics history |
| `de_demo_airflow_logs` | 25.99 MB | task logs used as phase evidence |
| `de-practicum-demo_de_demo_grafana_data` | 1.04 MB | dashboards |
| `de-practicum-demo_de_demo_iceberg_catalog` | 20.48 kB | Iceberg REST catalog |
| `de_demo_iceberg_catalog_backup_02a` | 20.48 kB | **explicit rollback artifact** — `STATE.md`: "SQLite remains preserved for rollback" |

### REPRODUCIBLE — safe to remove, regenerated on demand

| Item | Size | Regeneration cost |
|---|---|---|
| `/opt/spark/work/app-*` in `de-demo-spark-worker` | **~900 GB** | none — recreated on the next submit |
| `de_demo_spark_ivy_cache` (no container) | 1.424 GB | re-downloaded; needs network |
| `de-practicum-demo_de_demo_spark_ivy_cache` (no container) | 0 B | none |

Project images are technically reproducible but rebuilding is expensive; they
are ~30 GB total and are **not** recommended for removal.

### ORPHANED — no owner in this project

| Item | Size | Evidence |
|---|---|---|
| Volume `b420157…042f` | **22.5 GB** | a *stale Docker engine data root* (`containerd/`, `containers/`, `image/`, `engine-id 591dda73-…`). Its 21 container dirs match no live container; the live root is `/var/lib/docker` inside the VM. Dated Aug 9, no references. |
| `03-orchestration_kestra_postgres_data` | 69.45 MB | project `03-orchestration`, container exited 7 weeks ago |
| `03-orchestration_kestra_data` | 1.765 MB | same project |
| Containers `op-rabbitmq`, `op-redis` + volumes | ~2.4 MB | different project, exited 7–8 weeks ago |
| Container `cranky_newton` | 4.1 kB | anonymous leftover |
| ~6 small unlabeled dangling volumes | 0 B – 2.3 MB | no container, no compose labels |

Orphaned total ≈ **22.6 GB**, almost entirely the one stale engine root.

### UNKNOWN — decide before touching

- **`de-demo-kafka` is `exited`.** The broker is down, which is not explained by
  this investigation and matters for the streaming checkpoint story. Its two
  anonymous volumes are 0 B.
- **Four containers carry hash-prefixed duplicate names**
  (`7a18cc079146_de-demo-spark-connect`, `ff8f77f41bc2_de-demo-orders-producer`,
  `661e2fdcf3d3_de-demo-kafka-ui`,
  `e31fb53765ba_de-demo-observability-exporter`) — leftovers of a previous
  compose run that got renamed rather than replaced. Small, but it means the
  running stack does not match a clean `compose up`.
- `de-demo-airflow-db-init` exited one-shot; its volume is 0 B.

## 5. Host disk versus VM disk — the part that bites later

| Measure | Value |
|---|---|
| `C:\Users\serge\AppData\Local\Docker\wsl\disk\docker_data.vhdx` | **991.3 GB** |
| VM filesystem total / used | 1006.9 GB / ~938 GB |
| Host `C:` free | 2.3 TB |

**Deleting the 900 GB inside the VM will not shrink the vhdx.** It grows on
demand and never contracts on its own. Returning that space to `C:` needs an
explicit compaction — Docker Desktop → *Troubleshoot → Clean / Purge data*, or
`wsl --manage docker-desktop-data --set-sparse true`, or `Optimize-VHD`. Until
then `C:` keeps ~991 GB allocated even after a successful cleanup.

## 6. Recommended sequence (not executed)

1. `docker stop de-demo-orders-streaming` — halts 230 GB/h. Stopping preserves
   the Spark checkpoints; it is not a reset, and it matches the recorded
   fail-closed decision in `STATE.md`.
2. Delete `/opt/spark/work/app-*` → ~900 GB inside the VM.
3. Remove orphan volume `b420157…` → 22.5 GB. Verify `engine-id` differs from
   the live engine first (it does, as of this run).
4. Remove the `03-orchestration` and `op-*` volumes/containers if those projects
   are dead → ~71 MB.
5. Compact the vhdx to return space to `C:`.
6. Land the config fixes so it cannot recur:
   - `SPARK_WORKER_OPTS: "-Dspark.worker.cleanup.enabled=true -Dspark.worker.cleanup.interval=1800 -Dspark.worker.cleanup.appDataTtl=7200"`
   - stop re-staging 612 MB per submit — the jars are already baked into the
     image at `/opt/spark/h1-jars`, so a `spark.executor.extraClassPath` or a
     shared mount removes the `--jars` copy entirely
   - a `logging:` block with `max-size` / `max-file` on every service
   - bound the restart loop for a job that is deliberately fail-closed
7. Re-measure and record reclaimed host space.

## 7. Still open

The original request — a retention job for old *records* — is unanswered. The
candidate tables (`marts.lakehouse_metrics`, which `Metrics.record()` writes one
row per writer batch and medallion cycle, plus `marts.maintenance_runs` and
`marts.pipeline_runs`) could not be measured because Postgres is down. That
sizing should be redone once the stack is healthy; on current evidence it is a
correctness/tidiness concern, not a disk-space one.
