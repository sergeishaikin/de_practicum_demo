# Roadmap: Incremental Lakehouse Demo

## Milestones

- ✓ **Architecture and remediation baseline** — M1–M5, R1/R2, O1, S1, S1.1,
  H1, S1.2A, S1.2A.1, and S1.2B completed and verified at `89953fe`.

- 🚧 **B2 Controlled Rollout** — execute the accepted B2 architecture under
  controlled canary, evidence gate, cutover, and telemetry observation.

## Phases

### Phase 1: B2 Controlled Rollout

**Goal**: Drain legitimate post-migration B2 work safely, prove M5 cutover
conditions, observe real B2 cost, and make an evidence-based D-3a/O2 decision.

**Depends on**: S1.2B verified cleanup at `89953fe`.
**Requirements**: [CAN-01, CAN-02, CAN-03, CUT-01, CUT-02, TEL-01, DEC-01]
**Plans**: 7 plans
Plans:
**Wave 1**

- [ ] 01-01-PLAN.md — Canary preflight and frozen state verification.

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-02-PLAN.md — Controlled B2 canary with SILVER_MODE=b2, GOLD_SOURCE=legacy, SHADOW_COMPARE=1.

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-03-PLAN.md — Drain and verify the 255 legitimate post-migration manifests.

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-04-PLAN.md — Collect and evaluate M5 cutover evidence.

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 01-05-PLAN.md — Switch Gold to persisted Silver only after a green M5 gate.

**Wave 6** *(blocked on Wave 5 completion)*

- [ ] 01-06-PLAN.md — Collect a representative O1 telemetry window.

**Wave 7** *(blocked on Wave 6 completion)*

- [ ] 01-07-PLAN.md — Decide D-3a, O2, or no-change and record the rollout result.

## Conditional and Backlog Work

- **D-3a**: Open only if telemetry shows material scan/write amplification.
- **O2**: Open only if O1 diagnostics are insufficient.
- **F-305**: `marts` DDL ownership cleanup.
- **F-306**: Remove runtime `sys.path` mutation.
- **F-709**: Decide whether the legacy PostgreSQL serving path remains needed.
- **F-308**: Separate writer and medallion image/source ownership.
- Multi-writer support remains deferred.

## Progress

**Execution Order:** Phase 1 → 01-01 → 01-02 → 01-03 → 01-04 → 01-05 → 01-06 → 01-07

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. B2 Controlled Rollout | Current | 0/7 | Ready to plan | - |

Historical milestones are intentionally summarized above rather than
replayed as unfinished GSD phases.
