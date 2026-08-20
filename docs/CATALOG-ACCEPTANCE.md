# Milestone 3 catalog acceptance receipt

Date: 2026-08-20. This is the final local acceptance record for NG-0.3. It
does not archive the milestone or start NG-0.4.

## UI acceptance

The canonical UI flow is defined against the same API entities below. The
OpenMetadata server is reachable at `http://localhost:18585` and the entity
FQN is `lakehouse_trino.iceberg.gold.orders_daily_metrics`.

| User action | Entity | Result | Evidence |
| --- | --- | --- | --- |
| Search/open entity | Gold table | API entity exists with FQN `lakehouse_trino.iceberg.gold.orders_daily_metrics`, ID `dbf113ea-597d-4deb-88a0-e82e7a3ead7a` | `GET /api/v1/tables/name/...` |
| Inspect schema/columns | Gold table | Columns and descriptions returned by the table API | `fields=columns,tags,owners,domains` |
| Inspect owner/domain | Gold table | `streaming-platform`, `orders` | Same API response and ownership receipt |
| Open lineage/impact | Gold table | API returns Silver upstream, Bronze transitive upstream, and dbt semantic downstream | `GET /api/v1/lineage/table/name/...` |
| Visual UI navigation/screenshot | Gold table | **BLOCKED in this run**: no browser runtime was connected, so no screenshot or click-through claim is made | Browser runtime returned `No browser is available` |

The API graph contains no Kafka → Spark → landing edge. That missing edge is
truthful NG-0.2 behavior, not an inferred UI relationship. UI acceptance is the
only remaining mandatory gate before declaring NG-0.3 ready.

## Duplicate entity search

The catalog was searched across all table entities for the target names and
alternate service/FQN forms.

| Source | Service | FQN | Entity ID | Relationship type |
| --- | --- | --- | --- | --- |
| Trino/Iceberg discovery | `lakehouse_trino` | `lakehouse_trino.iceberg.bronze.orders` | `e46d66f9-f890-4ffb-9f67-4e77b9b8a858` | intended physical Bronze table |
| Trino/Iceberg discovery | `lakehouse_trino` | `lakehouse_trino.iceberg.silver.orders_clean` | `6051f0f5-811f-44d9-946f-38f1f1fb2949` | intended physical Silver table |
| Trino/Iceberg discovery | `lakehouse_trino` | `lakehouse_trino.iceberg.gold.orders_daily_metrics` | `dbf113ea-597d-4deb-88a0-e82e7a3ead7a` | intended physical Gold table |
| PostgreSQL discovery | `warehouse_postgres` | `warehouse_postgres.dwh.stg.orders` | `164d38e2-a01f-4b42-aa61-bec0dc9474aa` | distinct warehouse staging asset |
| PostgreSQL discovery | `warehouse_postgres` | `warehouse_postgres.dwh.core.orders` | `47cc1748-8748-4bc8-902e-116d912148d8` | distinct warehouse core asset |

No accidental aliases such as `iceberg.silver.orders_clean` or
`trino.iceberg.silver.orders_clean` were found. The PostgreSQL entities are
truthfully distinct from the Iceberg physical tables.

## Runtime lineage

| Edge | Emitter | Run ID | OpenMetadata edge | UI visible | Duplicate runtime claim? |
| --- | --- | --- | --- | --- | --- |
| landing → Bronze | NG-0.2 writer | not emitted | no edge | not applicable | no |
| Bronze → Silver | `iceberg-medallion` | `617654c9-2b09-51fa-9d68-34d2cb02668a` | `e46d66f9...` → `6051f0f5...`, source `OpenLineage` | API confirmed; UI screenshot pending | no |
| Silver → Gold | `iceberg-medallion` | `809ec936-32fa-5ba2-8dbb-d8e5c84b8db2` | `6051f0f5...` → `dbf113ea...`, source `OpenLineage` | API confirmed; UI screenshot pending | no |

Static dbt relationships coexist as `DbtLineage` downstream topology (for
example Gold → `daily_order_metrics`); they do not replace or duplicate the
OpenLineage runtime claims.

## dbt quality context

| Project/model/source | dbt evidence | Visible in OpenMetadata | Authority |
| --- | --- | --- | --- |
| Warehouse models | dbt 1.12.2; 4 models; 83 successful run-results, including test unique IDs | 105 dbt test cases indexed; current test-case status is `Unprocessed`, so OM is not treated as latest result authority | dbt |
| Warehouse staging sources | Freshness config present: warn after 30 minutes, error after 2 hours | Configuration is in artifacts; no freshness result was present in `run_results.json` | dbt |
| Warehouse core sources | Freshness explicitly unset | NOT APPLICABLE | dbt |
| Semantic models | dbt 1.12.2; 2 models; 28 successful run-results | dbt tests indexed as test cases; latest result remains in dbt artifacts | dbt |
| Semantic Iceberg sources | Freshness explicitly unset | NOT APPLICABLE | dbt |

No OpenMetadata quality test was created to manufacture a result. OpenMetadata
is the consumer/presenter; dbt remains execution and result authority.

## BI coverage

| Existing BI/reporting surface | OM support | Integrated? | Gap |
| --- | --- | --- | --- |
| Superset | Repository has Superset and dbt dashboard exposure | PARTIAL | No Superset service/connector is configured in the metadata profile; one exposure warning reports missing `meta.open_metadata_fqn` |
| Metabase | Existing local BI service | UNSUPPORTED in this profile | No Metabase connector path is configured |
| `reports/demo_quality_report.html` | Repository-rendered report | NOT APPLICABLE | File report is not a catalog service |

No new BI platform was introduced.

## Credential matrix

| Source | Identity | Read operations | Write denial | Limitation |
| --- | --- | --- | --- | --- |
| PostgreSQL warehouse | `metadata_reader` | CONNECT, schema USAGE, SELECT | CREATE/INSERT/UPDATE/DELETE all denied by live probes | none for warehouse reader |
| Airflow 3.3.1 | `metadata_reader` | JWT exchange at `POST /auth/token`, then connector GETs for `/api/v2/version`, `/dags`, `/tasks`, `/dagRuns`, `/taskInstances` | Identity is effectively admin because `AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True`; connector source code issues no POST/DELETE state operations | local demo security limitation; changing auth architecture is out of NG-0.3 scope |
| Trino/Iceberg | `metadata_reader` request identity, unauthenticated local Trino | metadata/catalog reads | not provable: local Trino has no auth policy separating writes | local security limitation |
| Kafka | no-auth local PLAINTEXT broker | topic metadata and dedicated lineage-topic consumption | no write-denial claim; ingestion does not publish to business topics or commit the runtime producer groups | local PLAINTEXT/no Schema Registry |
| dbt artifacts | read-only mounted `/opt/metadata-artifacts` | manifest/catalog/run-results reads | container mount is read-only | dbt job owns artifact generation |

## Resource receipt

| Component/state | Vendor guidance | Repository config | Measured local |
| --- | --- | --- | --- |
| OpenMetadata server | Production sizing is vendor guidance, not local acceptance | pinned 1.13.3 image, 512 MiB JVM starting heap | 840 MiB RSS; healthy |
| OpenSearch | Production sizing is vendor guidance, not local acceptance | single-node, 512 MiB JVM, isolated volume | 1.24 GiB RSS; healthy |
| Metadata Postgres | Production sizing is vendor guidance, not local acceptance | isolated pinned Postgres volume | 147 MiB RSS; healthy |
| Ingestion process | bounded CLI worker, not a scheduler | pinned image, one-shot workflows | 82 MiB RSS while idle; healthy |
| Permanent metadata profile | not production sizing approval | 4 long-running containers; 3 named metadata volumes | ~2.31 GiB RSS; DB 89.5M, search 14.2M, artifacts 6.9M |
| Core + metadata host snapshot | not production sizing approval | 20 core + 4 metadata running containers | selected core services plus metadata ~5.14 GiB RSS; Docker reports 15.49 GiB container memory limit |

This is a measured local demo envelope only, not production sizing approval.

## Rebuild receipt

| Logical entity | Before FQN | After FQN | Ownership stable | Lineage restored |
| --- | --- | --- | --- | --- |
| Bronze | `lakehouse_trino.iceberg.bronze.orders` | same | `streaming-platform` / `orders` | yes, as Bronze → Silver downstream edge |
| Silver | `lakehouse_trino.iceberg.silver.orders_clean` | same | `streaming-platform` / `orders` | yes, Bronze → Silver and Silver → Gold |
| Gold | `lakehouse_trino.iceberg.gold.orders_daily_metrics` | same | `streaming-platform` / `orders` | yes, Silver → Gold and dbt downstream |
| Warehouse mart | `warehouse_postgres.dwh.marts.v_sales_daily` | same | `data-platform` / `orders` | dbt topology restored |

Entity UUIDs changed after metadata-only volume deletion, as expected. FQNs,
cardinality, ownership/domain assignments, and lineage are the stable contract.
Canonical PostgreSQL/Kafka/Iceberg state was not deleted or reset.

## Failure injection

| Failure | Data path | Metadata signal | Recovery |
| --- | --- | --- | --- |
| OpenMetadata server stopped for 20s | writer and medallion remained `running` | API/container outage observable; server returned healthy after restart | server healthy |
| OpenSearch stopped for 20s | writer and medallion remained `running` | OpenSearch health failed while stopped; catalog dependency recovered after restart | OpenSearch and server healthy |
| OpenLineage ingestion consumer stopped for 20s | writer and medallion remained `running`; Kafka lineage high watermark stayed at 120 | ingestion container was stopped, so metadata lag/failure was observable | ingestion restarted healthy; runtime topic remained intact |

## Limitation classification

| Limitation | Type | Blocks NG-0.3? | Follow-up |
| --- | --- | --- | --- |
| dbt 1.12.2 works empirically outside documented OM range | Product compatibility limitation | No, explicitly qualified | revalidate on OM/dbt upgrades |
| local Docker host below vendor production sizing | Local environment limitation | No | use vendor sizing for production deployment |
| Kafka PLAINTEXT/no Schema Registry; Airflow all-admin SimpleAuthManager | Demo security limitation | No for local demo; must not be called production least privilege | harden auth separately |
| Kafka → Spark → landing OpenLineage event absent | Missing platform capability | No, truthful NG-0.2 boundary | add emitter in a later milestone |
| UI screenshot/click-through not captured because browser runtime unavailable | Acceptance evidence limitation | **Yes** | rerun UI acceptance with connected browser and attach screenshot/API correlation |

## Git state

- Commit: `b9e802c feat(metadata): add optional OpenMetadata catalog profile`
- Pushed to `fork/test/dbt-extensive-testing`
- Tree: clean after the commit; no staged or untracked implementation files
- Generated `__pycache__` and runtime artifacts are ignored
- No token/JWT/password was added to the committed scope
- Automatically triggered CI IDs: none observed in this local run
