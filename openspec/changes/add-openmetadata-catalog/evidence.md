# OM-PREFLIGHT evidence report

Date: 2026-08-20  
Change: `add-openmetadata-catalog`  
Scope: Milestone 2 only; no Milestone 3 Compose profile or emitter change was
implemented.

## Exit classification

**PASS_WITH_EXPLICIT_LIMITATIONS**

The OpenMetadata control plane and the required read-oriented catalog paths are
functional in an isolated opt-in harness. The limitations below are material
for production planning, but none disproves the NG-0.3 capability boundary.

## Candidate and immutable identities

- OpenMetadata stable release: `1.13.3-release` (the `2.0.0-rc2-release`
  pre-release was not selected).
- Server, linux/amd64 digest:
  `openmetadata/server@sha256:6c878281973d9e2c366e9da4f256a744acf67b1e53195fab67c3191e504e4169`.
- Ingestion, linux/amd64 digest:
  `openmetadata/ingestion@sha256:fe5effad9dbce98852b2f588905a4a8926c3c03de97fcceac8fe8e3ec927d717`.
- OpenSearch 3.3.0, linux/amd64 digest:
  `opensearchproject/opensearch@sha256:59e9e49ac00f19c2af9094e367c8e6586f7d07e6c06465c3f4c43b40934309f2`.
- Dedicated metadata Postgres image digest:
  `docker.getcollate.io/openmetadata/postgresql@sha256:4b225b4fcc810983c5e4578c690477688beaa587457310a5f4c615700334e321`.

Primary sources consulted: [OpenMetadata 1.13.3 release](https://github.com/open-metadata/OpenMetadata/releases/tag/1.13.3-release), [Docker deployment](https://docs.open-metadata.org/latest/deployment/docker), [production requirements](https://docs.open-metadata.org/v1.13.x/deployment/production-ready-requirements), [bare-metal compatibility](https://docs.open-metadata.org/v1.13.x/deployment/bare-metal), [OpenLineage](https://docs.open-metadata.org/v1.13.x/connectors/pipeline/openlineage), [Airflow](https://docs.open-metadata.org/v1.13.x/connectors/pipeline/airflow), [Kafka](https://docs.open-metadata.org/v1.13.x/connectors/messaging/kafka), [Trino](https://docs.open-metadata.org/v1.13.x/connectors/database/trino), [dbt](https://docs.open-metadata.org/v1.13.x/connectors/database/dbt), and [Iceberg](https://docs.open-metadata.org/v1.13.x/connectors/database/iceberg).

## Evidence matrix

| Hypothesis | Result | Evidence and explicit limitation |
| --- | --- | --- |
| H1 server candidate | PASS | Fresh isolated start; migration exited 0; `/healthcheck` reported server/database healthy; `/api/v1/system/version` returned `1.13.3`; UI/API exposed on the opt-in ports. |
| H2 persistence isolation | PASS | Fresh named `om_preflight_pg` volume and dedicated `openmetadata_db`/`openmetadata_user`; canonical warehouse and Airflow databases were not used for metadata writes. |
| H3 search compatibility | PASS_WITH_LIMITATION | OpenSearch 3.3.0 started, indexed/searchable entities, and recovered after restart. A single-node restart reports yellow status with unassigned replica shards; production must configure replica/shard policy for the deployment topology. |
| H4 Airflow | PASS | Existing repository Airflow 3.3.1 v2 API was queried through the connector; four existing DAGs were resolved. The harness's internal Airflow is only the official ingestion worker, not a second repository scheduler. |
| H5 dbt and column lineage | PASS_WITH_LIMITATION | Warehouse dbt 1.12.2 compiled 4/4 models; semantic dbt compiled 2/2. OpenMetadata parsed manifest/catalog/run-results and indexed real columns. `v_sales_daily` and `current_orders` returned `DbtLineage` column edges. Vendor docs list dbt Core through 1.9, so 1.12.2 remains an explicit compatibility watch item; exposure analysis and an `app` owner produced non-fatal warnings. |
| H6 Kafka metadata | PASS_WITH_LIMITATION | Dedicated `om-preflight-lineage` topic was discovered with one partition and no active consumer group. Kafka metadata ingestion completed with zero errors; optional Schema Registry check failed because no registry was configured, and sample-data/schema extraction was intentionally out of scope. |
| H7 Trino/Iceberg authority | PASS | Existing Trino discovered `iceberg.semantic.current_orders` and related tables. OpenMetadata indexed the physical FQNs under the Trino service; semantic dbt lineage resolved upstream `iceberg.silver.orders_clean` without creating a second physical authority. |
| H8 OpenLineage transport | PASS_WITH_LIMITATION | An isolated OpenLineage `RunEvent` was emitted to Kafka using the repository event shape and decoded by the OpenMetadata ingestion package (`COMPLETE`, one input, one output). Full production emitter wiring and indexed event-edge ownership remain Milestone 3 work; no emitter semantics were changed here. |
| H9 secrets, read-only, outage | PASS_WITH_LIMITATION | Temporary workflow files contained a runtime JWT only and were removed before commit. No secret was committed. Connector probes issued reads only, but the existing warehouse `app` credential was not proven to be a dedicated read-only role. Kafka was local PLAINTEXT. Stopping OpenSearch left the data plane untouched and the control plane recovered after restart; production fail-open counters/alerts remain implementation work. |
| H10 opt-in/reproducibility/cost | PASS_WITH_LIMITATION | The exact harness was destroyed with `down -v --remove-orphans` and rebuilt from fresh volumes; migration exit 0 and server health passed again. It is opt-in and isolated. Local capacity is below vendor production guidance (receipt below), so this is not a production-sizing approval. |

## Three-way resource receipt

| Resource | Vendor guidance | Repository/harness allocation | Measured local observation |
| --- | --- | --- | --- |
| OpenMetadata server | 4 vCPU / 16 GiB / 100 GiB (production-ready docs) | No Compose CPU/memory limit; JVM `-Xmx512m -Xms256m` | 783 MiB RSS, 2.69% CPU at capture |
| Metadata Postgres | 4 vCPU / 16 GiB / 100 GiB | No Compose limit; isolated named volume | 169 MiB RSS, 11.40% CPU at capture |
| OpenSearch | 2 vCPU / 8 GiB / 100 GiB | No Compose limit; JVM `-Xms512m -Xmx512m` | 1.18 GiB RSS, 1.43% CPU at capture |
| Ingestion worker | Vendor sizing is workload-dependent | Immutable ingestion image; no host limit | 2.387 GiB RSS, 10.57% CPU at capture |
| Whole local Docker engine | Not a vendor production target | Docker reports 8 CPUs and 15.49 GiB available | All 15 running containers: 11.85 GiB RSS; host RAM 31.73 GiB; C: free 2.24 TB |

Image sizes at capture: server 403 MiB, ingestion 1.68 GiB, OpenSearch 980 MiB.
The harness used no floating metadata image tags and no broad host bind mounts.

## Isolation, authority, and rollback

- State was confined to the `om-preflight` Compose project, its named volumes,
  and its `om-preflight_app_net` network. The only Kafka fixture was the
  dedicated `om-preflight-lineage` topic; stale streaming checkpoints and
  business topics were not reset or mutated.
- Trino remains the physical Iceberg authority. dbt remains the semantic/model
  authority. OpenLineage remains the runtime-edge authority. FQNs are aliases
  only when they resolve to the same physical object; no inferred edges were
  accepted.
- The temporary profile was removed with the exact project-scoped
  `docker compose ... down -v --remove-orphans`; core Airflow and Trino,
  started only for read-only probes, were returned to their prior stopped
  state. No canonical data volume was removed.

## DataHub fallback decision

The DataHub fallback trigger was **not reached**. OpenMetadata demonstrated the
required control-plane, Airflow, dbt/model+column, Kafka-topic, and
Trino/Iceberg paths. DataHub should be evaluated only if a future production
probe finds a material OpenMetadata gap (for example, inability to preserve
runtime-edge authority or to support the repository dbt version without
semantic rewrites).

## Boundary

This report closes Milestone 2. No Milestone 3 implementation may start until
the operator explicitly replies `CONTINUE`.
