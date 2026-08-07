<!-- generated-by: gsd-doc-writer -->
# Deployment

## Deployment targets

This project is a local, single-host demo platform. Deployment means running the Docker Compose stack on a machine with Docker; there is no hosted deployment configuration.

| Target | Config files |
|---|---|
| Full extended stack | `docker-compose.yml` + `docker-compose.extended.yml` |
| Base batch stack (PostgreSQL + Airflow) | `docker-compose.yml` |
| Offline base stack (pre-built local Airflow image) | `docker-compose.local-airflow.yml` |

Images referenced by tag (`postgres:15`, `apache/kafka:4.0.0`, `trinodb/trino:483`, `apache/superset:latest-dev`, `metabase/metabase:v0.54.6`, `minio/minio:RELEASE.2025-04-22T22-12-26Z`, `tabulario/iceberg-rest:latest`) come from public registries. Four images are built locally from Dockerfiles:

| Image | Dockerfile | Used by |
|---|---|---|
| `de-practicum-demo-airflow:0.1.0` | `airflow.Dockerfile` | `de-demo-airflow` |
| Spark image | `spark/Dockerfile` | `spark-master`, `spark-worker`, `spark-connect`, `orders-streaming` |
| Jupyter image | `jupyter/Dockerfile` | `jupyter` |
| PyIceberg image | `iceberg/Dockerfile` | `iceberg-writer`, `iceberg-medallion` |

## Build pipeline

No CI/CD pipeline is detected — there is no `.github/workflows/` directory. The "build" is a local step: build the images, then start the stack.

```powershell
.\stack.ps1 build
.\stack.ps1 up
.\stack.ps1 status
```

Or directly:

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml -f .\docker-compose.extended.yml build
docker compose --env-file .\.env -f .\docker-compose.yml -f .\docker-compose.extended.yml up -d
```

## Environment setup

1. Copy `.env.example` to `.env` and review the values (`Copy-Item .env.example .env`).
2. Set `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` to non-default secrets if the stack is exposed beyond localhost.
3. Set `SUPERSET_SECRET_KEY` — required by the Superset services (see [CONFIGURATION.md](CONFIGURATION.md)).
4. Start and verify with `scripts\doctor.cmd` (or `bash scripts/doctor.sh`) and `docker compose ps`.

Secrets are passed as environment variables to containers (`MINIO_ROOT_*`, `SUPERSET_SECRET_KEY`, `DWH_PASSWORD`). Trino credentials are injected at container start by `trino/etc/start-trino.sh` from `TRINO_S3_ACCESS_KEY` / `TRINO_S3_SECRET_KEY` (both set from the MinIO credentials in `docker-compose.extended.yml`), so no credential is committed in `trino/etc/catalog/iceberg.properties`.

## Rollback procedure

There is no automated rollback. Recovery options, from least to most destructive:

1. **Restart services** — `.\stack.ps1 down` (keeps volumes), then `.\stack.ps1 up`. Persistent state (MinIO objects, Iceberg catalog, Postgres data, Superset/Metabase config) is preserved.
2. **Reset local data** — `.\stack.ps1 reset` (or `reset -Force`) removes the named Docker volumes. This deletes MinIO objects, the Iceberg catalog (`de_demo_iceberg_catalog`), writer state (`de_demo_iceberg_writer_state`), Postgres data, and BI configuration. It is the effective "factory reset" of the demo.
3. **Revert code** — rebuild from a previous commit: `git checkout <commit>`, then `.\stack.ps1 build` and `.\stack.ps1 up`.
4. **Iceberg time travel** — for data-level rollback without touching volumes, query or restore a previous table snapshot from Trino:

```sql
SELECT count(*) FROM iceberg.bronze.orders FOR VERSION AS OF <snapshot_id>;
SELECT count(*) FROM iceberg.bronze.orders FOR TIMESTAMP AS OF TIMESTAMP '<timestamp> UTC';
```

## Monitoring

There is no external monitoring (no Sentry, Datadog, OpenTelemetry, or alerting configured). Operational visibility comes from the stack itself:

- Container health: `.\stack.ps1 status` / `docker compose ps`; healthchecks are defined for `de-demo-kafka`, `de-demo-spark-connect`, `de-demo-iceberg-rest`, and `de-demo-postgres`.
- Logs: `.\stack.ps1 logs -Service <name>`.
- Diagnostics: `scripts\doctor.cmd` (environment) and `scripts\run_checks.cmd` (SQL quality gates).
- Pipeline audit: the `marts.pipeline_runs` table records the status of every Airflow DAG run.
- UIs: Spark Master UI (`http://localhost:18080`), Kafka UI (`http://localhost:18090`), MinIO console (`http://localhost:19001`), Trino (`http://localhost:18082`).

<!-- VERIFY: the host ports above are the defaults from .env.example; they change if *_HOST_PORT variables are overridden in .env -->
