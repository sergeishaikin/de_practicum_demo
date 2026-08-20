# Milestone 3 catalog acceptance receipt

Date: 2026-08-20. This is the final local acceptance record for NG-0.3. It
does not archive the milestone or start NG-0.4.

## UI acceptance

OpenMetadata is reachable at `http://localhost:18585`. The target entity is
`lakehouse_trino.iceberg.gold.orders_daily_metrics`, entity ID
`dbf113ea-597d-4deb-88a0-e82e7a3ead7a`.

| User action | Result | Evidence |
| --- | --- | --- |
| Search/open entity | Real Explore search for `gold.orders_daily_metrics` returned the target FQN; the result was clicked | OpenMetadata UI, host Chrome headless, 2026-08-20 17:32 local |
| Inspect schema/columns | Gold page showed 7 columns and Iceberg `gold` schema context | [`docs/evidence/openmetadata-gold-overview.png`](evidence/openmetadata-gold-overview.png) |
| Inspect owner/domain | UI showed owner `Streaming Platform` and domain `Orders` | [`docs/evidence/openmetadata-gold-overview.png`](evidence/openmetadata-gold-overview.png) |
| Open lineage/impact | Gold lineage tab showed Bronze, Silver, Gold, and the dbt semantic consumer; the landing Container was opened separately and its lineage tab showed landing -> Bronze -> Silver | [`docs/evidence/openmetadata-gold-lineage.png`](evidence/openmetadata-gold-lineage.png), [`docs/evidence/openmetadata-landing-container-lineage.png`](evidence/openmetadata-landing-container-lineage.png) |

The screenshots correlate to the same API records (`GET /api/v1/tables/name/...`,
`GET /api/v1/containers/name/...`, and `GET /api/v1/lineage/table/name/...`).
The landing node is visibly a Container, not a fabricated Table. The known
Kafka -> Spark -> landing gap is not fabricated.

The sanitized API receipt is checked in at
[`docs/evidence/openmetadata-landing-container-lineage.json`](evidence/openmetadata-landing-container-lineage.json).

Container correlation: FQN
`landing_object_store.de-practicum.p_acceptance-20260820171302_x2f_orders__raw`, ID
`d160b55c-ce1d-468e-bd59-9cc08b9807e7`; parent StorageService
`landing_object_store`, ID `73e6907c-17da-4ba5-b718-06b5bc9a3d95`.

## Duplicate entity search

| Service | FQN | Entity ID | Relationship type |
| --- | --- | --- | --- |
| `lakehouse_trino` | `lakehouse_trino.iceberg.bronze.orders` | `e46d66f9-f890-4ffb-9f67-4e77b9b8a858` | intended physical Bronze table |
| `lakehouse_trino` | `lakehouse_trino.iceberg.silver.orders_clean` | `6051f0f5-811f-44d9-946f-38f1f1fb2949` | intended physical Silver table |
| `lakehouse_trino` | `lakehouse_trino.iceberg.gold.orders_daily_metrics` | `dbf113ea-597d-4deb-88a0-e82e7a3ead7a` | intended physical Gold table |
| `warehouse_postgres` | `warehouse_postgres.dwh.stg.orders` | `164d38e2-a01f-4b42-aa61-bec0dc9474aa` | distinct warehouse staging asset |
| `warehouse_postgres` | `warehouse_postgres.dwh.core.orders` | `47cc1748-8748-4bc8-902e-116d912148d8` | distinct warehouse core asset |

No accidental aliases such as `iceberg.silver.orders_clean` or
`trino.iceberg.silver.orders_clean` were found.

## Runtime lineage

| Edge | Emitter | Run ID | OpenMetadata result | UI |
| --- | --- | --- | --- | --- |
| landing -> Bronze | NG-0.2 writer + object-store compatibility adapter | `2f38572d-9b8b-556b-92d5-bb0208365f44` | Container `landing_object_store.de-practicum.p_acceptance-20260820171302_x2f_orders__raw` -> Bronze `e46d66f9-f890-4ffb-9f67-4e77b9b8a858`; API `lineageDetails.source=OpenLineage` | Visible in Container lineage UI |
| Bronze -> Silver | `iceberg-medallion` | `617654c9-2b09-51fa-9d68-34d2cb02668a` | `e46d66f9...` -> `6051f0f5...`, source `OpenLineage` | Visible |
| Silver -> Gold | `iceberg-medallion` | `809ec936-32fa-5ba2-8dbb-d8e5c84b8db2` | `6051f0f5...` -> `dbf113ea...`, source `OpenLineage` | Visible |

Static dbt relationships coexist as `DbtLineage` downstream topology; they do
not replace or duplicate the runtime OpenLineage claims.

### Landing -> Bronze reconciliation

Classification: **COMPATIBILITY_ADAPTER_FIX**.

The earlier `not emitted` receipt entry was incorrect. A safe isolated epoch
(`acceptance-20260820171302-epoch`) was used without resetting the operator-owned
Spark checkpoint, changing `failOnDataLoss`, wiping Kafka, or fabricating an
event. The real writer consumed two Parquet files and emitted one COMPLETE
OpenLineage event through `de-practicum-lineage`:

- input DatasetRef: `s3://de-practicum/acceptance-20260820171302/orders_raw`;
- output DatasetRef: `iceberg://iceberg-rest/bronze.orders`;
- load ID: `b4e02abb5c514234a4e5f853d80307be`;
- Iceberg snapshot: `2931379549083890160`;
- run ID: `2f38572d-9b8b-556b-92d5-bb0208365f44`.

The official OpenMetadata runtime ingestion remains primary. The narrow
consumer-side adapter then consumed the same actual event, created a
deterministic `CustomStorage` service plus bucket/prefix Containers, and added
the cross-entity edge with `lineageDetails.source=OpenLineage`; its lineage
details also retain the writer job, run ID, and input DatasetRef. The writer
semantics remain unchanged and the event is not relabelled as Kafka input.
The adapter is self-disabling: it checks the native edge first, ignores
non-object-store or malformed datasets, and produces zero changes on replay.

The truthful graph is therefore:

```text
KNOWN MISSING (by design): Kafka -> Spark -> landing
EXPECTED, EMITTED, INDEXED: landing Container -> Bronze
INDEXED AND VISIBLE:        Bronze -> Silver -> Gold
```

## dbt quality context

dbt 1.12.2 remains execution/result authority: 4 warehouse models, 83
successful warehouse run-results, 2 semantic models, and 28 successful
semantic run-results were indexed as context. OpenMetadata test cases remain
`Unprocessed`; no synthetic quality result was created. Staging freshness is
configured (warn 30 minutes, error 2 hours); core and semantic freshness are
explicitly unset.

## BI coverage

Superset is present in repository/dashboard exposure but has no configured
metadata connector; Metabase has no connector path. The rendered HTML report is
not a catalog service. No BI platform was introduced.

## Credential and resource limitations

- PostgreSQL metadata reader was probed read-only (CONNECT/USAGE/SELECT; no
  CREATE/INSERT/UPDATE/DELETE).
- Airflow local SimpleAuthManager is all-admin; the connector issues GET-only
  reads. This is a demo security limitation, not a production least-privilege
  claim.
- Trino is unauthenticated locally; Kafka is PLAINTEXT without Schema Registry.
- The measured metadata profile is local-demo evidence, not production sizing:
  four long-running containers used approximately 2.31 GiB RSS.

## Rebuild and failure receipts

Metadata-only rebuild preserved the Bronze/Silver/Gold/warehouse FQNs,
ownership/domain assignments, cardinality, and indexed medallion lineage;
entity UUID changes were expected. Canonical PostgreSQL/Kafka/Iceberg state was
not deleted or reset.

During 20-second failure injections (metadata server, OpenSearch, and the
OpenLineage ingestion consumer), writer and medallion data paths remained
running and the runtime topic remained intact; all services recovered healthy.

## Remaining known gap and status

The only remaining intentional gap is Kafka -> Spark -> landing OpenLineage
emission, which is outside NG-0.2's current compatibility boundary.

**MILESTONE 3 STATUS: COMPLETE**

**NG-0.3 READY FOR MILESTONE 4: YES**

The landing -> Bronze event is real, the catalog representation is a
deterministic Container, the edge retains OpenLineage source semantics, and the
UI/API evidence is captured. NG-0.3 may close; do not begin Milestone 4 in this
turn.

## Git state

- Prior implementation commits remain `b9e802c` and `ae25727`, pushed to
  `fork/test/dbt-extensive-testing`.
- This receipt correction, the compatibility adapter/tests, three screenshot
  evidence files, and the sanitized API JSON receipt are the intended new
  tracked paths.
- No token, JWT, password, browser profile, cache, or downloaded binary is
  included.
