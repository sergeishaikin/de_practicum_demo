# Phase 02: Warehouse Asset-Orchestrated Batch Split - Context

**Gathered:** 2026-08-16
**Status:** Ready for planning
**Source:** Recorded user decisions and accepted architecture note

<domain>
## Phase Boundary

Replace the combined manual warehouse DAG with a manual ingestion DAG and an
Asset-triggered marts validation/publication DAG. Preserve current SQL,
business rules, view storage, scheduling frequency, and non-warehouse runtime
ownership.

</domain>

<decisions>
## Implementation Decisions

### Workflow boundary

- **D-01:** `warehouse_orders_ingestion` is manual-only and owns staging load,
  exact staging parity, the complete `10_rebuild_core.sql` transaction,
  read-only core readiness, and final core Asset publication.
- **D-02:** `warehouse_marts_validation` is scheduled only by the
  `core.orders` Asset and owns marts readiness, payment reconciliation, mart
  Asset publication, and the existing idempotent audit.
- **D-03:** TaskGroups represent real staging/core and validation/publication
  stages only; they must not add decorative tasks.

### Asset and failure semantics

- **D-04:** The final ingestion publisher emits `core.orders` and
  `core.order_items` events only after every upstream ingestion task succeeds.
- **D-05:** `validate_core` only proves both core tables are queryable and
  captures row counts. Zero rows is allowed and no new business rule is added.
- **D-06:** Core Asset event `extra` contains JSON-serializable `row_count`
  metadata. It does not duplicate a run ID or contain secrets.
- **D-07:** Downstream provenance comes from
  `triggering_asset_events` and `AssetEvent.source_dag_run.run_id`; a missing
  or invalid Asset event fails closed.

### Audit migration

- **D-08:** Preserve `marts.pipeline_runs.run_id` as the downstream DagRun
  primary key. Add nullable `ingestion_run_id` with a non-unique index; leave
  historical rows `NULL` and add no duplicate marts-run column.
- **D-09:** The migration is additive and idempotent for both fresh and
  existing PostgreSQL volumes.

### Storage and scope fence

- **D-10:** Marts remain views; Phase 02 adds no build, refresh, or
  materialization.
- **D-11:** Existing SQL expressions, staging parity, payment reconciliation,
  audit quality rules, and idempotency remain unchanged.
- **D-12:** Maintenance, medallion, streaming, recovery, checkpoints, and
  Bronze/Silver/Gold ownership remain unchanged.

### Verification

- **D-13:** Automated evidence includes unit, DagBag, Gherkin BDD, migration,
  verifier, regression, and read-only receipt tests.
- **D-14:** Live proof triggers ingestion exactly once and follows the native
  Asset event to the automatically created downstream DagRun and exact audit
  provenance. Upstream-failure behavior is proven without publishing live
  state.

### the agent's Discretion

- Exact TaskGroup identifiers and bounded timeout values, provided the DAG
  graph remains operationally honest and retries stay fail-closed.
- Internal helper names and the format of machine-readable runtime evidence.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/notes/warehouse-asset-orchestration-boundary.md` - accepted
  architecture and scope fence.
- `.planning/REQUIREMENTS.md` - ORCH-01 through ORCH-08 acceptance contract.
- `AGENTS.md` - repository verification and runtime safety contract.
- `db/pipeline_sql/10_rebuild_core.sql` - unchanged core rebuild transaction.

</canonical_refs>

<deferred>
## Deferred Ideas

Airflow-owned medallion is a later evaluation seed only. Materialized marts,
maintenance redesign, streaming ownership, recovery redesign, and new DQ rules
are outside Phase 02.

</deferred>

---

*Phase: 02-warehouse-asset-orchestrated-batch-split*
*Context gathered: 2026-08-16 from recorded decisions*
