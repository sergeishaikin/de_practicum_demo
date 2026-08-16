---
title: Warehouse Asset orchestration boundary
date: 2026-08-16
context: Airflow orchestration roadmap Phase 1 / project GSD Phase 2
status: accepted
---

# Warehouse Asset Orchestration Boundary

## Decision

Split the current combined manual warehouse DAG into two operationally honest
Airflow 3.3.1 workflows:

1. `warehouse_orders_ingestion` remains manually triggered and owns staging
   load, exact staging parity, the complete core rebuild transaction, read-only
   core readiness counts, and final core Asset publication.
2. `warehouse_marts_validation` is scheduled by the successfully published
   `core.orders` Asset and owns marts validation, payment reconciliation, mart
   Asset publication, and the existing pipeline audit.

This is project GSD Phase 2, but Phase 1 of the separate Airflow orchestration
roadmap discussed with the user.

## Data and failure contract

- `db/pipeline_sql/10_rebuild_core.sql` remains whole and owned by ingestion.
- `validate_core` only proves that `core.orders` and `core.order_items` are
  queryable and captures their row counts. Zero rows is metadata, not a new
  failure condition.
- The final producer task emits `core.orders` and `core.order_items` events
  only after load, staging validation, core rebuild, and readiness all succeed.
- `core.orders` schedules the downstream DAG. Both core events may carry
  publication metadata such as `row_count`; secrets and duplicated run IDs do
  not belong in event `extra`.
- The downstream DAG reads the source ingestion ID from
  `triggering_asset_events` and `AssetEvent.source_dag_run.run_id`.
- A failed or skipped producer path emits no scheduling event. Failed marts
  validation or reconciliation does not certify publication success.

## Audit migration

Use an additive migration for `marts.pipeline_runs`:

- preserve `run_id` as the downstream/marts DagRun primary key;
- add nullable `ingestion_run_id`;
- leave historical values `NULL`;
- add a non-unique index on `ingestion_run_id`;
- do not add a duplicate `marts_run_id` column or rename `run_id`.

## Storage and ownership constraints

- Marts remain PostgreSQL views. The downstream DAG validates and publishes
  them; it does not materialize or rebuild them physically.
- `lakehouse_maintenance` keeps its verified mapped runtime model.
- `iceberg-medallion` remains a long-running service with its current cycle.
- Kafka/Spark streaming, checkpoints, recovery/idempotency, and
  Bronze/Silver/Gold publication remain unchanged.

## UI and operational metadata

Both DAGs use truthful display names, descriptions, structured tags,
`doc_md`, owner/criticality metadata, one active run, bounded timeouts, and an
explicit fail-closed retry policy. TaskGroups are used only when they expose a
real operational stage; they must not create decorative work.

## Why this boundary

The split introduces a real Asset-scheduled dependency while keeping the
manual ingestion frequency and current business transformations intact. It
improves UI clarity and cross-DAG provenance without moving medallion or
streaming ownership into Airflow and without inventing mart materialization.

## Primary Airflow references

- https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/asset-scheduling.html
- https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/assets.html
