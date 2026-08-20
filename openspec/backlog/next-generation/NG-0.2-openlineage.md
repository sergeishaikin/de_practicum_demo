# NG-0.2 — OpenLineage Runtime Lineage Protocol

> **Lifecycle:** DONE
> **Disposition:** ADOPTED
> **Implemented by:** `add-openlineage-runtime-lineage`
> **Archived change:** `openspec/changes/archive/2026-08-20-add-openlineage-runtime-lineage/`
> **Original role:** pre-implementation specification
>
> **This document is historical intent, not current behaviour.** It records what
> was proposed before implementation, and its present-tense statements describe
> the repository as it was *before* this item landed. Current truth lives in
> `openspec/specs/`, the repository documentation, the code and the tests.
> Reading this file as a description of today is how solved work gets re-solved.
>
> One requirement was **not** met and is recorded rather than quietly dropped:
> the Spark listener is not installed, because OpenLineage publishes no build for
> Spark 4.2, so the `Kafka -> landing` edge is not emitted. See the change's
> evidence and `docs/LINEAGE.md`.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Freshness of external assumptions

Versions, compatibility matrices, resource requirements, connector capabilities and product limitations recorded in this item are planning assumptions, not frozen truths. They were recorded against the baseline branch named above and are not re-verified while the item sits in the backlog.

- **WHEN** this item is promoted to an authorised change
- **THEN** every externally time-sensitive premise SHALL be re-verified against primary documentation before the design is accepted
- **AND** a premise that cannot be re-verified SHALL be recorded as unverified rather than carried forward on the authority of this document.

## Product decision

Use **OpenLineage** as the vendor-neutral runtime lineage event protocol. It is not the final UI. OpenMetadata is the planned first backend/UI in NG-0.3, but first-party runtime emitters SHALL remain replaceable by changing transport configuration rather than rewriting lineage semantics.

## Goal

Produce trustworthy runtime lineage for the actual processing graph, including orchestration, streaming and first-party PyIceberg/medallion boundaries, while avoiding duplicate or contradictory lineage edges from multiple collectors.

## Dependencies

NG-0.1 must be accepted first.

## Non-goals

- No catalog/governance UI in this change.
- No automatic claim that every Spark/Flink/Python operation yields column lineage.
- No production Flink deployment.
- No duplicate ingestion of the same lineage edge merely to improve UI density.
- No Marquez deployment as the primary catalog.

## ADDED Requirements

### Requirement: OpenLineage is the runtime protocol boundary

First-party runtime lineage added by this program SHALL be representable as OpenLineage jobs, runs, datasets and facets wherever OpenLineage can express the relationship.

Product-specific catalog APIs MAY supplement a proven gap but SHALL NOT replace the OpenLineage contract for ordinary runtime lineage.

### Requirement: Airflow uses the native provider path

The existing Airflow 3.x installation SHALL use the maintained `apache-airflow-providers-openlineage` integration rather than the legacy `openlineage-airflow` package.

#### Scenario: SQL-native Airflow task emits lineage

- **WHEN** a supported SQL-native task completes
- **THEN** the native provider emits its runtime event
- **AND** no parallel custom emitter produces a conflicting duplicate edge.

#### Scenario: Python task has non-inferable datasets

- **WHEN** a first-party Python task reads/writes datasets that the provider cannot infer
- **THEN** explicit lineage metadata/events are emitted for those datasets
- **AND** the event names use the canonical dataset naming contract from NG-0.1.

### Requirement: Spark integration is proven before global activation

The OpenLineage Spark listener SHALL be tested against the repository's actual Spark runtime and submission modes before it is injected globally.

A documentation claim for Spark in general SHALL NOT substitute for a live compatibility test against this repository's Spark 4.2 stack.

#### Scenario: Listener breaks Spark startup or UI

- **WHEN** the listener/agent is incompatible with the current Spark runtime
- **THEN** the integration remains disabled
- **AND** the blocker and fallback/custom event path are documented rather than downgrading Spark silently.

### Requirement: First-party PyIceberg services emit explicit dataset boundaries

`iceberg-writer` and `iceberg-medallion` SHALL emit OpenLineage events or an equivalent OpenLineage-compatible adapter for their actual input/output dataset boundaries.

At minimum the graph SHALL be able to represent landing/bronze/silver/gold relationships and attach actual Iceberg snapshot IDs where available.

### Requirement: dbt lineage has one authoritative ingestion path per edge class

Detailed dbt model and column lineage SHOULD be sourced from dbt artifacts through the metadata integration in NG-0.3 unless a measured reason requires OpenLineage dbt events.

If both mechanisms are enabled, the design SHALL define deduplication/authority rules and prove that one logical edge is not represented as contradictory duplicates.

### Requirement: Runtime lineage SHALL reflect actual runs

A lineage run event SHALL reference the real run/cycle/load identifiers available at execution time. Static DAG topology SHALL NOT be presented as proof that a particular runtime read/write occurred.

### Requirement: Failure is observable but non-corrupting

If the lineage backend is unavailable, the data-processing job SHOULD continue when its business semantics remain safe. Failed lineage delivery SHALL be logged/metricized and, where the selected transport supports it, buffered/retried within bounded limits.

### Requirement: Flink lineage is capability-gated

NG-1.1 SHALL include a compatibility spike for the then-selected Flink/OpenLineage integration. Automatic connector lineage SHALL NOT be assumed for Iceberg until proven with the selected Flink/Iceberg/OpenLineage versions.

If connector coverage is incomplete, custom OpenLineage events SHALL be used only for the missing boundaries and SHALL be covered by tests.

### Requirement: Dataset naming is stable

Dataset namespace/name construction SHALL be deterministic across Airflow, Spark, Python services, dbt, Kafka, Trino and future Flink. The same physical/logical dataset SHALL NOT appear under avoidable aliases caused by hostnames or ephemeral container IDs.

## Non-functional requirements

- **Backend portability:** transport/backend change without emitter redesign.
- **Idempotency:** replaying metadata delivery must not create semantically different duplicate assets.
- **Latency:** runtime events should be visible within an explicitly measured bound; the initial bound may be provisional but must be labeled as such.
- **Security:** auth token is least-privilege and not present in emitted facets/logs.
- **Overhead:** job runtime impact measured on representative small and larger executions.
- **Schema stability:** emitted event schema/version pinned through dependency lock.

## Required tests

- unit tests for dataset-name canonicalization and facets;
- negative test for duplicate lineage emitters on the same edge;
- live Airflow provider smoke;
- Spark listener compatibility smoke before global enablement;
- custom PyIceberg lineage event test using captured event JSON;
- backend-down test proving business-data processing remains correct and failure is observable.

## Acceptance graph

The change is not complete until a live lineage receipt can show an actual path equivalent to:

```text
Kafka orders topic
  → streaming processing job
  → landing / bronze.orders
  → silver.orders_clean
  → gold.orders_daily_metrics
```

Airflow/dbt edges MAY be completed in NG-0.3 when dbt/catalog ingestion is added, but any missing edge must be explicit rather than inferred.

## External compatibility note

OpenLineage documentation currently directs Airflow 2.7+ users to the native provider and provides Spark/Flink integrations. Flink connector coverage varies by integration generation; implementation SHALL re-check the exact compatibility matrix at apply time.

## Rollback

Disable the OpenLineage provider/listener/custom emitter configuration while leaving processing code semantics unchanged. Rollback SHALL NOT require reverting canonical data.

## Hard stops

Stop if producing correct lineage requires changing canonical table ownership, source data semantics, or a processing engine version. Such a change requires its own architecture spec.
