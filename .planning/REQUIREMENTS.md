# Requirements: Incremental Lakehouse Demo

**Defined:** 2026-08-09
**Core Value:** Business-key current state must remain correct and recoverable while the pipeline processes only committed incremental work.

## Validated historical requirements

- [x] **DOM-01**: `business_version` survives Kafka → Landing → Bronze unchanged and is not derived from Kafka offset — M1.
- [x] **COM-01**: Bronze accepts only committed Landing files and preserves writer load-id recovery semantics — M2.
- [x] **SIL-01**: B2 Silver resolves monotonic business versions and preserves global `order_id` uniqueness — M3.
- [x] **REC-01**: B2 recovers crash-before-commit and crash-after-Silver-commit without duplicate state — M3.
- [x] **GOLD-01**: Persisted Silver can feed Gold only through controlled shadow/cutover evidence — M4/M5.
- [x] **OBS-01**: Runtime correctness, recovery, performance, and shadow metrics are observable — O1.
- [x] **SEM-01**: dbt semantic views, lineage, exposures, and contracts are reproducible — S1/S1.1.
- [x] **RUN-01**: Clean-stack runtime is pinned and reproducible — H1.
- [x] **HAND-01**: Historical outbox handoff can be proven, recovered, and cleaned without changing data files — S1.2A–S1.2B.

## Active rollout requirements

### Canary

- [x] **CAN-01**: B2 runs with `SILVER_MODE=b2`, `GOLD_SOURCE=legacy`, and `SHADOW_COMPARE=1` while Gold remains on the legacy projection.
- [ ] **CAN-02**: All 255 legitimate post-migration manifests drain with zero unresolved progress, FF-14 conflicts, or shadow mismatches.
- [x] **CAN-03**: Bronze/Silver correctness and dbt 26/26 remain green throughout the canary.

### Cutover and evidence

- [ ] **CUT-01**: M5 evaluator is green before `GOLD_SOURCE=persisted_silver` is enabled.
- [ ] **CUT-02**: Persisted-Silver Gold remains under shadow comparison during the observation window and rollback remains verified.
- [x] **TEL-01**: O1 captures representative B2 files planned, bytes planned, files added/removed, Silver duration, keys processed, snapshots, and recovery state.
- [ ] **DEC-01**: The telemetry gate records exactly one outcome: open D-3a, open O2, or retain both deferred.

## Planned orchestration requirements

### Warehouse ingestion boundary

- [ ] **ORCH-01**: Replace `demo_core_marts_pipeline` with two honestly named Airflow 3.3.1 DAGs: manual `warehouse_orders_ingestion` and Asset-triggered `warehouse_marts_validation`, each with human-readable display name, description, structured tags, owner/criticality metadata, `doc_md`, one active run, bounded timeouts, and an explicit fail-closed retry policy.
- [ ] **ORCH-02**: `warehouse_orders_ingestion` preserves the existing staging load, exact four-table non-empty staging parity, and the complete transactional `db/pipeline_sql/10_rebuild_core.sql` without changing SQL expressions, schemas, counts, transformations, or scheduling frequency.
- [ ] **ORCH-03**: After core rebuild, a read-only readiness task proves `core.orders` and `core.order_items` are queryable and captures both row counts without minimum, non-empty, null, grain, or other new business rules. Asset events are published only after this task and every prior ingestion task succeeds; failed or skipped ingestion publishes no event.
- [ ] **ORCH-04**: The final ingestion publisher emits `core.orders` and `core.order_items` events with JSON-serializable row-count metadata. `core.orders` is the scheduling boundary for `warehouse_marts_validation`; `core.order_items` remains explicit lineage. The downstream DAG obtains the source ingestion DagRun ID from `triggering_asset_events` / `AssetEvent.source_dag_run.run_id`, not duplicated Asset `extra` metadata.

### Marts validation and provenance

- [ ] **ORCH-05**: Apply an additive migration to `marts.pipeline_runs`: preserve `run_id` unchanged as the downstream/marts DagRun primary key, add nullable `ingestion_run_id`, keep historical rows `NULL`, and add a non-unique index on `ingestion_run_id`.
- [ ] **ORCH-06**: `warehouse_marts_validation` performs read-only marts validation, the existing payment reconciliation, successful mart Asset publication, and the existing idempotent audit. Marts remain views; Phase 2 introduces no physical mart build, refresh, or materialization.
- [ ] **ORCH-07**: New TaskGroups improve UI readability without hiding the operational boundary or creating decorative tasks. The audit records current downstream `run_id` plus source `ingestion_run_id`, and failure at validation or reconciliation prevents successful publication/audit certification.
- [ ] **ORCH-08**: Automated unit, Gherkin BDD, DagBag, migration, Asset-trigger/provenance, and read-only E2E receipt tests prove the split and its failure semantics. `lakehouse_maintenance`, `iceberg-medallion`, Kafka/Spark streaming ownership, recovery/idempotency, checkpoints, and Bronze/Silver/Gold publication remain unchanged.

## Deferred requirements

- **LAY-01**: Tune D-3a physical layout only after measured scan/write amplification.
- **TRACE-01**: Add O2 tracing only if O1 cannot diagnose the observed behavior.
- **OPS-01**: Address F-305, F-306, F-709, and F-308 in a separate backlog wave.

## Out of Scope

| Feature | Reason |
|---------|--------|
| B2 canary plus Gold cutover in one uncontrolled switch | Canary and M5 evidence must remain independently reversible. |
| D-3a before telemetry | No production evidence currently justifies physical tuning. |
| New orchestration engine | Existing Spark/Airflow ownership is accepted for this rollout. |
| Multi-writer support | Single active medallion processor remains an accepted current-scale risk. |
| Physical mart materialization | Marts remain views; a build/refresh contract would change storage semantics. |
| Airflow-owned medallion processing | Evaluation is a seed after Phase 2 verification, not a current requirement. |
| New core business-quality thresholds | Phase 2 adds queryability and row-count metadata only. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CAN-01 | Phase 1 | Complete |
| CAN-02 | Phase 1 | Pending |
| CAN-03 | Phase 1 | Complete |
| CUT-01 | Phase 1 | Pending |
| CUT-02 | Phase 1 | Pending |
| TEL-01 | Phase 1 | Complete |
| DEC-01 | Phase 1 | Pending |
| ORCH-01 | Phase 2 | Pending |
| ORCH-02 | Phase 2 | Pending |
| ORCH-03 | Phase 2 | Pending |
| ORCH-04 | Phase 2 | Pending |
| ORCH-05 | Phase 2 | Pending |
| ORCH-06 | Phase 2 | Pending |
| ORCH-07 | Phase 2 | Pending |
| ORCH-08 | Phase 2 | Pending |

**Coverage:**

- Active rollout requirements: 7 total
- Planned orchestration requirements: 8 total
- Mapped to phases: 15
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-09*
*Last updated: 2026-08-16 after adding the warehouse Asset-orchestration phase contract*
