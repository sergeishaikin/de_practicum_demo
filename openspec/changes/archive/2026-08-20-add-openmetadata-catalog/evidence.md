# NG-0.3 evidence

## Milestone 2 — OM-PREFLIGHT

Date: 2026-08-20  
Change: `add-openmetadata-catalog`  
Historical scope: Milestone 2 preflight only; the implementation evidence
below was collected later and is intentionally not folded into this original
receipt.

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

## Historical boundary

This report closed Milestone 2. The operator subsequently reviewed the report
and explicitly replied `CONTINUE`; Milestone 3 implementation then proceeded.
The preflight boundary is retained as historical evidence and is not a current
claim that implementation is absent.

## Milestone 3 — implementation and local acceptance

Milestone 3 implementation and local acceptance are complete through commit
`04f0402`. The durable detailed acceptance receipt is
[`docs/CATALOG-ACCEPTANCE.md`](../../../docs/CATALOG-ACCEPTANCE.md); the
evidence below keeps the archived OpenSpec change self-contained.

### Commits

- `b9e802c` — added the optional OpenMetadata catalog profile and immutable
  metadata configuration.
- `ae25727` — recorded the first metadata acceptance Git receipt.
- `c0be99a` — reconciled runtime lineage evidence and captured Gold UI proof.
- `04f0402` — implemented the object-store Container compatibility adapter,
  focused tests, final acceptance docs, screenshots, and API receipt.

### Implementation

The permanent metadata profile contains isolated persistence, immutable
OpenMetadata/OpenSearch images, bootstrap/configuration, source connectors for
PostgreSQL, Airflow, Kafka, Trino/Iceberg, OpenLineage, and both dbt artifact
surfaces. A dbt 1.12.2 compatibility guard, ownership/domain seeding, and
explicit BI coverage classification are checked in.

The official OpenMetadata OpenLineage workflow remains primary. The narrow
metadata-side adapter supplements only the proven object-store representation
gap:

```text
real OpenLineage s3 DatasetRef
    -> deterministic StorageService/Container
    -> existing Bronze Table
```

It preserves `source=OpenLineage`, job/run/input correlation, deterministic
bucket/prefix identity, s3/s3a/s3n normalization, replay idempotency, and the
native-edge-first self-disabling guard. It does not rewrite the writer event,
create a fake Table, map Kafka as storage, or invent an upstream edge.

### Test receipt

The focused reconciliation implementation ran:

```text
45 passed, 5 deselected
ruff check: passed
black: passed
git diff --check: passed
```

The local runtime acceptance also ran the official runtime workflow: 42
OpenLineage records processed, 0 warnings, 0 errors. Adapter replay produced
`0 edge(s)` after the native Container → Bronze edge existed.

### Runtime lineage

The accepted runtime IDs are:

| Edge | Run ID | Result |
| --- | --- | --- |
| landing → Bronze | `2f38572d-9b8b-556b-92d5-bb0208365f44` | real writer event; Container representation indexed |
| Bronze → Silver | `617654c9-2b09-51fa-9d68-34d2cb02668a` | indexed OpenLineage edge |
| Silver → Gold | `809ec936-32fa-5ba2-8dbb-d8e5c84b8db2` | indexed OpenLineage edge |

The only intentional remaining gap is Kafka → Spark → landing.

### UI and API evidence

- Gold overview: `docs/evidence/openmetadata-gold-overview.png`.
- Gold lineage: `docs/evidence/openmetadata-gold-lineage.png`.
- Landing Container lineage: `docs/evidence/openmetadata-landing-container-lineage.png`.
- Sanitized API receipt: `docs/evidence/openmetadata-landing-container-lineage.json`.

The accepted landing Container is
`landing_object_store.de-practicum.p_acceptance-20260820171302_x2f_orders__raw`
with ID `d160b55c-ce1d-468e-bd59-9cc08b9807e7`, full path
`s3://de-practicum/acceptance-20260820171302/orders_raw`, and an edge to
`lakehouse_trino.iceberg.bronze.orders` with `lineageDetails.source=OpenLineage`.
UUIDs may change after metadata-only rebuild; FQNs, ownership, domains, and
lineage are the stable logical contract.

### Quality, credentials, failure, resources, and rebuild

dbt remains execution/result authority; OpenMetadata presents indexed model,
column, test, and freshness context without creating a competing execution
truth. PostgreSQL write probes denied CREATE/INSERT/UPDATE/DELETE for the
metadata reader. Airflow SimpleAuthManager all-admin, local unauthenticated
Trino, and Kafka PLAINTEXT remain explicit demo limitations.

Metadata server, OpenSearch, and OpenLineage consumer failure injection left
the writer/medallion data paths running and recovered after restart. The
measured local permanent profile is approximately 2.31 GiB RSS for the metadata
services; vendor production guidance and local measurements remain separate.
Metadata-only destroy/rebuild preserved canonical source state while
reconstructing the logical catalog contract.

### Governance reconciliation note

The final Milestone 3 design and task list were reconciled after Milestone 3
local acceptance and before archive. This corrected stale preflight-scoped
change documents; it did not retroactively alter implementation history or
claim that the final design existed before the implementation.

## Milestone 4 — final verification and closure candidate

Date: 2026-08-20

Closure candidate: `f61448889db0ad1c1cc3f36ae82465fa83b067a6`
Branch: `test/dbt-extensive-testing`

### Local completion gates

The repository completion contract was run at the closure candidate:

| Gate | Result |
| --- | --- |
| `uv run --locked ruff check .` | PASS |
| `uv run --locked black --check .` | PASS; 95 files unchanged |
| `uv run --locked mypy` | PASS; 9 source files, no issues |
| `uv run --locked pytest` | PASS; 509 passed, 81 deselected |
| `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | PASS; 94.65% total |
| SQLFluff dbt model/test lint | PASS |
| Metadata contract and adapter tests | PASS; 12 passed |
| `.env.example` merged metadata Compose config | PASS |
| Backlog/OpenSpec/lifecycle validators | PASS before archive; rerun after archive |

### Final-head local metadata smoke

The final-head smoke reused the still-running accepted metadata profile and
did not mutate canonical core volumes. API version returned `1.13.3` (HTTP
200). The deterministic object-store Container was
`landing_object_store.de-practicum.p_acceptance-20260820171302_x2f_orders__raw`
(`d160b55c-ce1d-468e-bd59-9cc08b9807e7`, `deleted=false`) with full path
`s3://de-practicum/acceptance-20260820171302/orders_raw`. Its Bronze lineage
contained exactly one `OpenLineage` edge. Replaying the official runtime
adapter returned `Object-store compatibility adapter materialized 0 edge(s)`.

### Required live CI receipts

All required workflows were green for the same closure-candidate SHA:

| Workflow | Run | Result |
| --- | ---: | --- |
| CI | `32409960233` | success |
| H1 clean reproducible stack | `32409960155` | success |
| M5 architecture gates | `32409960154` | success |
| S1 dbt semantic lineage | `32409960158` | success |
| Metadata profile — isolated live acceptance | `32409960176` | success |

The Metadata profile run exercised fresh core dependencies, isolated
Bronze/Silver/Gold and Kafka fixtures, dbt artifact materialization and guard,
OpenMetadata bootstrap/API checks, static ingestion, ownership, an isolated
OpenLineage event, runtime ingestion, deterministic Container FQN/fullPath and
Bronze lineage assertions, replay idempotency, diagnostics, and metadata-only
cleanup.

### Causal failures resolved before acceptance

The first closure candidate failed only the newly introduced metadata gate for
three evidenced reasons: semantic dbt artifacts were generated without views;
the initial admin login was probed before the server was ready; and the CI
fixture omitted the `orders` topic required by the checked-in ownership map.
These were fixed respectively by materializing the semantic dbt stage, polling
for a successful login with the container script path, and creating the
isolated `orders` topic. Subsequent receipts above are green; no blind retry
was used.

### Closure decision and explicit limitations

The metadata profile remains opt-in and locally sized below vendor production
guidance. Airflow SimpleAuthManager, local unauthenticated Trino, Kafka
PLAINTEXT, dbt 1.12.2 compatibility watch, BI coverage limits, and the
intentional Kafka → Spark → landing lineage gap remain explicit limitations.
OpenMetadata remains the data UI/control-plane projection; dbt, Trino/Iceberg,
OpenLineage, and Grafana retain execution, storage, runtime-edge, and
operational-telemetry authority respectively. With the final local and live
gates green, NG-0.3 is ready to be archived and adopted.
