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

**Coverage:**

- Active requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-09*
*Last updated: 2026-08-10 after the 01-06 telemetry gate passed*
