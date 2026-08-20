# Lineage and provenance

Status: descriptive record of the implemented state. Axes 1-3 and the caveats
below describe the state at `d77b39a` (2026-08-18); the OpenLineage emission
section describes NG-0.2, added 2026-08-20.

This document describes what the repository records today, what each record
proves, and what it does **not** prove. It is deliberately not a design
proposal: no target platform, no catalogue, no new dependency is introduced
here. Work that is known to be missing is listed in
[Intentionally deferred](#intentionally-deferred) with the gate it waits on.

Read it before answering any "where did this row come from" question, because
the answer lives in three different places depending on which question is
actually being asked.

## Three axes

The project records three different things that are all loosely called
"lineage". Keeping them apart is the point of this document.

| Axis | Question it answers | Where it lives |
|---|---|---|
| **Structural lineage** | Which dataset or model is derived from which? | dbt manifests, Airflow Assets |
| **Execution and certification provenance** | Which execution produced or validated this state, and was it certified? | DagRun ids, `marts.pipeline_runs`, `marts.lakehouse_metrics` (`cycle_id`, `phase`), shadow comparison result |
| **Data-state provenance** | Which committed data state came from which prior state and which unit of work? | Iceberg snapshot properties, completion receipts, snapshot ids |

B2 completion receipts deliberately span the second and third axes: the same
artefact is both the proof that a load executed exactly once and the record of
which keys that load wrote. For a recovery-oriented design that overlap is a
property, not a modelling flaw — recovery reads the same artefact that lineage
would.

## 1. Structural lineage

### dbt — two separate graphs

| Project | Adapter | Sources | Models | Consumers declared |
|---|---|---|---|---|
| `lakehouse_semantic` (`dbt/`) | dbt-trino | `bronze.orders`, `silver.orders_clean`, `gold.orders_daily_metrics` | `current_orders`, `daily_order_metrics` (views) | `exposures:` -> Superset dashboard |
| `warehouse_transform` (`dbt/warehouse/`) | dbt-postgres | `stg.*` (4), `core.orders`, `core.order_items` | 4 mart views | `exposures:` -> demo quality report, SQL quality gates |

`dbt docs generate` produces `manifest.json`, `catalog.json` and `index.html`
under each project's `target/`. The warehouse artefacts are validated at
runtime by `warehouse_marts_validation` and are a publication precondition.

What this proves: model-to-model and source-to-model derivation inside one
project.

What it does not prove:

- Nothing links the two projects. Trino/Iceberg models and PostgreSQL models
  are two disconnected graphs with no shared node.
- Lineage is resource-level, not column-level. The pinned runtime is
  dbt-core 1.12.2 with dbt-trino 1.10.3 / dbt-postgres 1.11.0.
- The declared warehouse consumers are the two repository scripts that read the
  marts (`scripts/build_report.*` and `scripts/run_checks.*`). The Metabase
  chart script reads `marts.streaming_orders` from the streaming path, which is
  not a dbt model, so no BI tool appears in this graph — the PostgreSQL side
  ends at repository-owned analysis artefacts, not at a dashboard.

### Airflow Assets

The batch path is fully represented as URI-addressed Assets:

```text
file://<repo>/data/raw/olist_*.csv              Raw CSV
        |  warehouse_orders_ingestion
        v
postgres://<host>:5432/dwh/stg/<table>          PostgreSQL - Staging
        v
postgres://<host>:5432/dwh/core/orders          PostgreSQL - Core   <- scheduling boundary
postgres://<host>:5432/dwh/core/order_items     PostgreSQL - Core   <- lineage only (ORCH-04)
        |  warehouse_marts_validation (asset-triggered)
        v
postgres://<host>:5432/dwh/marts/<view>         PostgreSQL - Marts
postgres://<host>:5432/dwh/marts/pipeline_runs  PostgreSQL - Audit
```

`core/order_items` is published for lineage only; scheduling depends on
`core/orders` alone. This is required behaviour, not an accident (ORCH-04).

For the lakehouse path the DAG **explicitly publishes** one aggregate Asset,
`trino://de-demo-trino:8080/iceberg/semantic`, after the Cosmos group succeeds.
Cosmos may additionally emit per-model Assets under its default configuration;
that surface is currently unverified (see below).

What it does not prove:

- The streaming path is absent from the Asset graph. `iceberg-writer` and
  `iceberg-medallion` are long-running services, not Airflow tasks, so Bronze,
  Silver and Gold have no Asset representation at all.
- Per-model dbt Assets: `dags/warehouse_dbt.py` pins
  `RenderConfig(emit_datasets=False)` and passes `emit_datasets=False` to the
  freshness operator, so warehouse dbt nodes are deliberately not Assets.
  `dags/lakehouse_dbt_semantic.py` constructs no `RenderConfig`, so the Cosmos
  default governs it instead. Observed in the running `de-demo-airflow`
  container (Airflow 3.3.1, Cosmos 1.15, WATCHER mode): **Cosmos emits no
  Assets of its own in either DAG.** All six rendered tasks of the semantic
  group — two `.run` and two `.test` tasks plus `dbt_producer_watcher` and its
  `_done` partner — carry zero inlets and zero outlets, so the DAG's only Asset
  is the explicit `publish_semantic_asset` outlet. The warehouse group behaves
  the same way, as its `emit_datasets=False` intends. Both surfaces are now
  pinned by `tests/test_dags.py` (marked `airflow`; needs the container).

## 2. Execution and certification provenance

### `marts.pipeline_runs`

Written by `warehouse_marts_validation`:

- `run_id` — the marts DagRun (primary key).
- `ingestion_run_id` — the upstream ingestion DagRun, obtained from
  `AssetEvent.source_dag_run.run_id` and validated to be exactly one event from
  exactly `warehouse_orders_ingestion`. Historical rows are `NULL` (ORCH-05).
- Counts and reconciliation extremes: `stg_orders`, `stg_order_items`,
  `core_order_items`, `mart_sales_days`, `duplicate_grain_rows`,
  `null_key_rows`, `max_reconcile_diff`.
- `status`, computed fail-closed: any duplicate grain row, any null key, or
  `max_reconcile_diff > 0.01` marks the run failed and prevents publication.

This answers "which execution certified this publication", not "which datasets
this was derived from".

### `marts.lakehouse_metrics`

One row per writer batch and per medallion phase. Phase 4 identity columns:
`cycle_id`, `phase`, `bronze_snapshot_id`, `silver_snapshot_id`,
`gold_snapshot_id`. Rows written before Phase 4 have `cycle_id IS NULL`, and
that predicate is the documented interpretation rule for historical rows.

Note: **there is no `source_epoch_id` column here.** Epoch identity lives in
completion receipts only (see below).

### Shadow comparison

`compare_business_state()` returns `equal`, `mismatches`, `compared_keys` and
`excluded_columns`. It compares a whitelist:

```python
SHADOW_BUSINESS_COLUMNS = (
    "business_version", "customer", "amount",
    "country", "status", "event_time", "event_date",
)
SHADOW_EXCLUDED_COLUMNS = (
    "kafka_timestamp", "kafka_partition", "kafka_offset",
)
```

What it proves: for every compared key, the seven business columns agree
between the legacy candidate and the persisted B2 projection.

What it does not prove: `compare_business_state()` does not itself enforce
classification completeness. It iterates `SHADOW_BUSINESS_COLUMNS` and ignores
anything else, and reports `SHADOW_EXCLUDED_COLUMNS` as evidence without
checking it.

The completeness guarantee comes from the repository contract instead:
`tests/test_m4_gold.py::test_every_silver_column_is_classified_for_shadow_comparison`
asserts that every non-key `SILVER_SCHEMA` column is classified exactly once —
the two tuples partition the columns, and their intersection is empty. A column
added to Silver and registered in neither tuple fails CI rather than silently
dropping out of business-state equality at runtime.

## 3. Data-state provenance

### Iceberg snapshot properties

| Layer | Property | Written by |
|---|---|---|
| Bronze | `load-id` | `iceberg/writer/iceberg_writer.py` on every append |
| Silver | `silver-work-id`, `changed-keys` (count) | `iceberg/medallion/iceberg_medallion.py` on overwrite |
| Gold | — | not stamped yet; see deferred `04-05` |

Writer recovery re-checks `pending` load-ids against the table's snapshot
summaries and skips a re-append if the load is already committed. The lineage
record and the idempotency mechanism are the same field.

### B2 completion receipts

One immutable JSON object per `load_id`, written after the Silver commit by
`_append_completion_receipt()`:

| Field | Meaning |
|---|---|
| `manifest_id`, `load_id`, `sequence` | work identity and ordering |
| `source_paths` | the landing/Bronze inputs consumed |
| `source_epoch_id` | source epoch, when derivable — see caveats |
| `silver_snapshot_id` | the Silver snapshot this load produced |
| `changed_keys` | the resolved write set of `order_id`s |
| `output_digest` | digest of the resolved logical rows |
| `completed_at`, `result` | completion evidence |

Receipts are the recovery ledger as well: on restart, a load already present in
the receipt ledger is re-marked complete from the receipt rather than
reprocessed, carrying `source_epoch_id` and `output_digest` forward.

### Caveats that must not be overstated

These four points are the difference between an accurate and a flattering
description of this axis.

1. **`source_epoch_id` is receipt-only.** It is not a column of
   `marts.lakehouse_metrics` and not part of the in-memory progress record.
2. **Epoch derivation is conditional.** `_source_epoch_id()` returns a value
   only when the incoming rows carry exactly one distinct non-null epoch, and
   `None` otherwise. Rows with a null epoch are skipped rather than forcing
   `None`, so a partially stamped batch still records the single epoch it has.
   "We always know the source epoch of a load" is therefore false.
3. **`output_digest` is a logical digest, not bitwise equality.** It is
   `sha256(json.dumps(resolved, sort_keys=True, default=str))` — a digest of
   the resolved rows' serialised form. It does not assert that Parquet or
   Iceberg bytes are identical, and `default=str` makes it depend on Python's
   string form of non-JSON types rather than on a typed canonical encoding.
4. **`changed_keys` is the write set.** It is every `order_id` in `resolved`,
   that is every row the overwrite wrote — not a proven set of keys whose
   business state changed. Proving the narrower claim would require showing
   that resolution never rewrites a logically unchanged current row.

One further consequence: a single `order_id` legitimately appears in the
receipts of several successive loads. Answering "which load produced the
**current** state of this key" requires reducing receipts by `sequence` and
snapshot history. A Silver row carries no pointer to its producing load.

## What the current model cannot answer

- **Winner-event provenance.** Bronze carries `event_id`, `source_epoch_id`,
  `canonical_payload` and `canonical_payload_hash` (`BRONZE_LINEAGE_FIELDS`),
  and the streaming job validates the hash and deduplicates on `event_id`.
  `SILVER_SCHEMA` has eleven fields and `_rows_to_silver()` projects exactly
  those eleven, so none of the four reaches Silver. Given a current Silver row,
  the loads whose write sets included that key are recoverable; identifying
  which one produced the current state requires the receipt and snapshot
  reduction described above. The specific Bronze event that won the
  `business_version` contest is not recoverable at all.
- **Column-level lineage** — nowhere, on any axis.
- **A cross-subsystem join.** See identity boundaries below.
- **An end-to-end graph.** The only Kafka-to-BI representation is prose and
  diagrams in `README.md`, `docs/ARCHITECTURE.md`,
  `docs/semantic/S1-dbt-lineage.md` and this file. Nothing verifies those
  diagrams against the running system.

## Identity boundaries

The same physical relation is named differently in each subsystem, and no
canonical form is defined:

| Subsystem | Form | Example |
|---|---|---|
| Airflow Assets | URI with path segments | `postgres://de-demo-postgres:5432/dwh/marts/v_sales_daily` |
| Airflow Assets (lakehouse) | URI, schema granularity | `trino://de-demo-trino:8080/iceberg/semantic` |
| dbt | relation name | `marts.v_sales_daily` |
| Iceberg | catalog identifier | `iceberg.silver.orders_clean` |
| Kafka | topic | `orders` |
| Landing | S3 prefix | `s3://de-practicum/streaming/orders_raw` |

Consequence: the graphs cannot be joined automatically today. A canonical
identity contract is what would let Airflow, dbt, Iceberg, Kafka and landing
identifiers be joined at all.

One thing this document deliberately does not claim: that hand-written and
Cosmos-generated Asset URIs collide. As observed and now pinned by
`tests/test_dags.py`, Cosmos emits no Assets at all in this deployment, so
today there is nothing to collide with — every Asset in the graph is
hand-written. Cosmos 1.15 on Airflow 3 uses slash-separated Asset URIs
(`database/schema/table`), the same shape as the hand-written ones, so if
dataset emission is ever enabled the two may or may not resolve to identical
strings. That comparison has never been run here. Run it before enabling the
warehouse dbt Asset surface; do not assume either outcome.

## OpenLineage emission (NG-0.2)

Runtime lineage is emitted as OpenLineage events by the boundaries that perform
the work. The executable contract is
[`iceberg/common/lineage.py`](../iceberg/common/lineage.py), exercised by
[`tests/test_lineage_contract.py`](../tests/test_lineage_contract.py) and
[`tests/integration/test_lineage_receipt.py`](../tests/integration/test_lineage_receipt.py).
Where this document and that module disagree, the module is the contract and
this file is the defect.

### What emits, and what it claims

| Job name | Input | Output | Run identity |
|---|---|---|---|
| `iceberg-writer.landing-to-bronze` | `s3://<bucket>/<landing prefix>` | `iceberg://<catalog>/bronze.orders` | `load_id`, plus the snapshot the append produced |
| `iceberg-medallion.bronze-to-silver` | `bronze.orders` | `silver.orders_clean` | `cycle_id`, source and produced snapshots |
| `iceberg-medallion.silver-to-gold` | `silver.orders_clean` | `gold.orders_daily_metrics` | `cycle_id`, source and produced snapshots |

Airflow tasks emit through `apache-airflow-providers-openlineage`, the
maintained provider for Airflow 3.x. The legacy `openlineage-airflow` package is
not used.

Each event carries a `provenance` run facet built from an NG-0.1
`ProvenanceEnvelope`, so the never-fabricate rule applies to lineage too: an
identifier a boundary does not have is absent **with a reason**, never derived.
Both long-running services declare `airflow.dag_run_id` absent — no Airflow run
launched them — and `trace_id` absent until NG-0.4 exists.

### Three rules

**An edge belongs to the boundary that performed it.** The writer holds Bronze
rows carrying `kafka_offset`, so a Kafka-to-Bronze edge is *derivable* there.
The writer never read Kafka; it read Parquet from the landing prefix. Emitting
that edge would make the graph lie about which job did what, and a false edge
propagates into every consumer, where a labelled hole can simply be closed.

**One output dataset has one owner.** `register_edge_owner()` is called at
service startup and raises if a second boundary claims an output another already
claims. Duplicate emitters produce contradictory edges that no consumer can
arbitrate, so this fails the service at startup rather than silently doubling
the graph. It is also the guard that will matter when NG-0.3 adds dbt lineage
over the same warehouse edges.

**Emission never touches the data path.** Every emit is wrapped, every failure
is counted, and processing continues. This inverts the repository's usual
fail-closed stance deliberately: a lineage backend outage must not become a data
outage. The counter is what keeps the fail-open behaviour honest — an emitter
that has been failing silently for a week is otherwise indistinguishable from
one that works.

### Dataset identity is configuration, never the host

Namespaces come from configured endpoints, normalised so one dataset has one
identity: scheme, credentials, port and trailing separators are dropped, so
`s3a://` and `s3://` spellings of one bucket agree and six spellings of the REST
catalog resolve to `iceberg://iceberg-rest`. A hostname or container id in a
namespace would rename every dataset on every restart, which is the alias defect
this contract exists to prevent.

### The transport is a file, not a backend

`OPENLINEAGE__TRANSPORT__*` selects the transport; this change writes
newline-delimited JSON to a shared volume. That is a receipt, not an operational
surface: it has no retention, query or deduplication. NG-0.3 repoints the same
emitters at OpenMetadata by changing configuration, which is the reason the
official client is used rather than hand-built event JSON.

### Object-store catalog compatibility (NG-0.3)

The pinned OpenMetadata 1.13.3 OpenLineage connector accepts the writer event
but does not materialize an S3 LOCATION-only input as a catalog node. The
metadata-side `openlineage_container_adapter.py` is a narrow, reversible
supplement for this proven representation gap:

1. It consumes the actual COMPLETE event from the dedicated lineage topic.
2. It accepts only normalized `s3://`/`s3a://`/`s3n://` inputs paired with an
   existing `iceberg://iceberg-rest` output table.
3. It deterministically maps `bucket + prefix` to
   `landing_object_store.<bucket>.<encoded-prefix>`, using a StorageService and
   nested Container entities. The original prefix remains in the Container's
   `prefix`/`fullPath`; credentials, hosts, run IDs, and container IDs are not
   part of identity.
4. It checks for a native edge before adding anything, then creates a
   `Container -> Table` edge with `lineageDetails.source=OpenLineage` and the
   job/run/input correlation from the actual event.

The adapter never rewrites the event, maps Kafka to storage, creates a landing
Table, or maintains a manual edge. Replaying the same event is a no-op, and a
future native OpenMetadata mapping automatically disables the supplement.

### The one edge this does not close

**`Kafka orders topic → streaming job → landing` is not emitted.** Verified
against primary sources on 2026-08-20: OpenLineage's Spark integration builds
variants `spark3` through `spark40`, and its `gradle.properties` pins
`spark40.spark.version=4.0.0`. There is no `spark41` or `spark42` module, and
this repository runs Spark **4.2.0**.

Injecting a listener built for a different Spark major-minor into the B2
exactly-once streaming job is an unproven binary-compatibility bet on the most
safety-critical service here, so the integration stays disabled and the gap is
recorded rather than the engine being changed to suit the tool. NG-1.1's
capability gate is the same pattern applied to Flink.

This gap is about the lineage *event*, not about traceability: NG-0.1's receipt
already proves Kafka position → `load_id` → Iceberg snapshot from stored state,
because Bronze rows carry `kafka_partition` and `kafka_offset` and the
`load-id` snapshot stamp joins them. What is missing is the emitted edge, and
closing it needs either an OpenLineage build for Spark 4.2 or a first-party
emitter inside the streaming job.

## Intentionally deferred

The active milestone is the B2 canary and the M5 cutover gate.
`.planning/PROJECT.md` scopes a new orchestration engine out, and the same
discipline applies to a lineage workstream.

| Deferred item | Gate |
|---|---|
| `source-silver-snapshot-id` on the Gold commit, giving the first explicit Silver-to-Gold provenance edge | Phase 4 plan `04-05` (planned, not executed) |
| Durable shadow certificate recording which snapshot pair was compared | Phase 4 plan `04-06` (planned, not executed) |
| Winner-event provenance (`event_id`, `canonical_payload_hash`) in Silver | own ADR after M5. Adding the columns does not by itself break shadow equality, because the comparator uses a whitelist — but the ADR must state explicitly that provenance metadata is excluded from business-state equality, and register the columns in `SHADOW_EXCLUDED_COLUMNS` |
| Canonical dataset identity across Airflow, dbt and Iceberg | **partly closed by NG-0.2** for the emitted surface (writer, medallion, Airflow); dbt and Trino relations still have no canonical form, and joining the dbt manifests to the emitted graph waits on NG-0.3 |
| Generated unified lineage artefact from the two manifests plus the Asset graph | after M5; replaces the hand-drawn diagram with a derived one |
| CI lineage contract (fail on an unclaimed critical dataset, a serving dataset with no declared consumer, or two ids for one relation) | after M5 |
| `emit_datasets=True` for the warehouse project | the current no-Cosmos-Assets baseline is pinned, so enabling it is now a visible, testable change: compare the URIs Cosmos then generates against the hand-written ones before keeping it |
| OpenLineage backend and catalogue UI | NG-0.3. NG-0.2 emits to a file transport; repointing is a configuration change |
| Column-level lineage | not scheduled |
| Kafka-to-landing lineage event | blocked: no OpenLineage Spark build for 4.2.0, see above |

Both gaps that were cheap enough to close without waiting for M5 are closed, and
neither changed runtime behaviour. Warehouse mart consumers are declared as dbt
`exposures:`. The semantic DAG's Asset surface was observed in the running
container and pinned, together with the publisher URIs of both warehouse DAGs;
`scripts/dump_dag_structure.py` now reports inlet and outlet URIs rather than
only counts, which is what made the surface observable at all.

Everything else in the table above stays deferred until after M5.
