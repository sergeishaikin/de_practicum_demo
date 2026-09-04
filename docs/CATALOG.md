# OpenMetadata catalog (optional local control plane)

The complete Milestone 3 acceptance receipt is in
[CATALOG-ACCEPTANCE.md](CATALOG-ACCEPTANCE.md).

OpenMetadata is an opt-in metadata consumer and data UI. It is not canonical
storage, an Airflow replacement, a dbt execution engine, a runtime lineage
producer, or the operational Grafana UI. The default stack is unchanged when
this profile is omitted.

## Start and stop

Use the repository `.env` for the core stack and copy the `METADATA_*` values
from `.env.example` (keep real passwords only in `.env` or a secret store).
Start the extended graph and metadata profile together:

```powershell
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml \
  -f docker-compose.metadata.yml --profile metadata up -d
```

The UI is at `http://localhost:18585`, the admin API at
`http://localhost:18586`, and local OpenSearch at `http://localhost:19200`.
State is isolated in named metadata volumes; do not remove core volumes,
Kafka checkpoints, Iceberg state, or the `dwh` database for catalog tests.

Stop only the metadata plane with the same Compose files and
`--profile metadata down`. Add `-v` only for an explicitly authorised
metadata destroy/rebuild test.

## Reproducible ingestion

The profile has no second scheduler. `metadata-ingestion` is an idle pinned
OpenMetadata CLI image; bounded one-shot services run repository-controlled
scripts:

```powershell
docker compose ... run --rm metadata-bootstrap
docker compose ... run --rm metadata-static-ingestion
docker compose ... run --rm metadata-ownership
docker compose ... run --rm metadata-ingestion python /opt/metadata/scripts/run_ingestion.py runtime
```

`bootstrap_catalog.py` creates the service graph, domains, and teams.
`run_ingestion.py` ingests PostgreSQL, Trino/Iceberg, Airflow, Kafka, dbt
artifacts, and OpenLineage. After the official OpenLineage workflow,
`openlineage_container_adapter.py` supplements only the pinned connector's
object-store LOCATION gap by materializing a deterministic StorageService /
Container hierarchy and a `source=OpenLineage` Container -> Table edge from the
actual event. `apply_ownership.py` applies the checked-in
`metadata/config/ownership.json`; ownership and domains are not UI-only.

dbt remains the execution authority. The dbt jobs generate fresh
`manifest.json`, `catalog.json`, and `run_results.json` into isolated
state. `assert_dbt_artifacts.py` fails unless the actual repository dbt
version is 1.12.2, expected models/sources, catalog columns, manifest
dependencies, and a dbt test result are present. This is empirical
compatibility evidence, not a claim that OpenMetadata officially supports
dbt 1.12.2 (the documented vendor range is older).

## Credential and authority matrix

| Source | Identity | Minimum/proven permission | Authority |
| --- | --- | --- | --- |
| PostgreSQL warehouse | `metadata_reader` | CONNECT, schema USAGE, SELECT on `core`, `stg`, `staging`, `marts`; no CREATE/DML | PostgreSQL/dbt for execution; OpenMetadata reads |
| Airflow API | `METADATA_AIRFLOW_USER` | Existing local REST read path; Simple Auth has no restricted role | Airflow for DAG/run metadata |
| Kafka | local PLAINTEXT broker | Topic metadata/read path; no business-topic mutation | Kafka connector for topic metadata |
| Trino/Iceberg | `metadata_reader` | Metadata/query path only | Trino for physical entity identity |
| OpenLineage | `openmetadata-runtime-lineage` | Read from dedicated `de-practicum-lineage` topic | NG-0.2 emitter for runtime edges |

The PostgreSQL reader is provisioned by `metadata/create-reader.sql`. The
negative proof must continue to show that it cannot CREATE, INSERT, UPDATE, or
DELETE in the warehouse. Airflow's local Simple Auth does not provide a
separately enforceable read-only principal; this is an explicit local
exception, not a production least-privilege claim. Kafka PLAINTEXT and the
absent Schema Registry are also explicit local-demo gaps.

## Lineage and identity

Runtime edges come only from real NG-0.2 emitters. In this profile the writer
and medallion send events to the dedicated Kafka topic using the pinned
`openlineage-python`/`confluent-kafka` dependencies. OpenMetadata consumes
them with `PipelineMetadata` and
`lineageInformation.dbServiceNames=[lakehouse_trino]`. The namespace mapping
resolves `iceberg://iceberg-rest` to the Trino service.

| Asset | OpenLineage identity | Catalog FQN |
| --- | --- | --- |
| Bronze | `iceberg://iceberg-rest / bronze.orders` | `lakehouse_trino.iceberg.bronze.orders` |
| Silver | `iceberg://iceberg-rest / silver.orders_clean` | `lakehouse_trino.iceberg.silver.orders_clean` |
| Gold | `iceberg://iceberg-rest / gold.orders_daily_metrics` | `lakehouse_trino.iceberg.gold.orders_daily_metrics` |

dbt topology is retained as `DbtLineage`; runtime edges remain
`OpenLineage` edges with their emitting pipeline and run facet. No
Kafka-to-Spark-to-landing edge is inferred; that NG-0.2 gap remains explicit.

For an object-store input that the pinned OpenMetadata connector cannot resolve
as a table, the adapter uses Option A (declarative Container materialization):
`landing_object_store.<bucket>.<encoded-prefix>` represents the exact
S3-compatible DatasetRef (slashes and underscores are collision-safe encoded in
the Container name; the original prefix remains in `displayName`, `prefix`,
and `fullPath`). It normalizes `s3://`, `s3a://`, and `s3n://` spellings,
excludes credentials/hosts/run IDs from identity, checks for a native edge
before adding anything, and is idempotent on replay. The edge stores the
OpenLineage source plus job/run/input correlation in `lineageDetails`. It
never maps Kafka inputs, invents a landing Table, or replaces the official
OpenLineage ingestion workflow.

## Acceptance evidence (2026-08-20)

- Immutable OpenMetadata 1.13.3 server/ingestion and OpenSearch images start
  with isolated metadata Postgres; migration and health checks pass.
- Airflow ingestion processed 42 records with 0 errors; PostgreSQL, Trino,
  Kafka, and both dbt workflows completed with 0 ingestion errors.
- A real medallion cycle emitted COMPLETE events for Bronze-to-Silver and
  Silver-to-Gold. OpenMetadata indexed both runtime edges; Gold API lineage
  shows the Silver upstream edge and dbt downstream semantic view.
- Deterministic owner/domain assignments were applied to core tables,
  pipelines, Iceberg assets, and Kafka topics from checked-in JSON.
- Single-node OpenSearch yellow is acceptable only when primaries are assigned,
  replicas are the sole unassigned shards, search works, and restart recovers.
- Fail-open smoke test: stopping only `de-metadata-server` for 20 seconds left
  `iceberg-writer` and `iceberg-medallion` running; the catalog API returned to
  `healthy` after restart.
- Metadata-only destroy/rebuild was exercised on
  `de_practicum_metadata_db_data`, `de_practicum_metadata_search_data`, and
  `de_practicum_metadata_dbt_artifacts`. After bootstrap, dbt guards, static
  ingestion, runtime ingestion, and ownership re-application, key FQNs each
  had exactly one entity and retained their assignments:
  `lakehouse_trino.iceberg.gold.orders_daily_metrics` →
  `streaming-platform`/`orders`; `warehouse_postgres.dwh.marts.v_sales_daily`
  → `data-platform`/`orders`. Entity UUIDs are expected to change on a clean
  rebuild; FQNs and cardinality are the stable identity contract.
- The rebuilt `metadata_reader` role passed negative probes for `CREATE`,
  `INSERT`, `UPDATE`, and `DELETE` (all denied) while catalog reads remained
  available.

The `.env.example` file is a template with placeholders. It must not be used
alone to recreate the core graph: load the real local `.env` for core
credentials and overlay the metadata variables, or use a secret store. A
placeholder core password can recreate Postgres/Trino containers and make the
read-only source-reader check fail.

Destroy/rebuild acceptance must compare entity FQNs and owner/domain values
before and after metadata-only state deletion. A changed FQN or duplicate
physical asset is a failure. Local resource measurements are demo evidence, not
production sizing approval.
