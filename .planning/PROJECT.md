# Incremental Lakehouse Demo

## What This Is

This repository is a reproducible Spark, Kafka, Iceberg, Trino, dbt, and
Superset demo for an incremental Bronze → business-key Silver → Gold
medallion. It demonstrates the migration from full-overwrite serving to a
PyIceberg-owned B2 current-state projection while preserving correctness,
recovery, lineage, and operational evidence.

## Core Value

Business-key current state must remain correct and recoverable while the
pipeline processes only committed incremental work.

## Requirements

### Validated

- [x] Domain `business_version` survives Kafka → Landing → Bronze and remains
  distinct from Kafka transport metadata — M1.
- [x] Bronze commit authority and writer recovery boundary are explicit — M2.
- [x] PyIceberg B2 Silver projection is monotonic, globally unique, and
  crash-recoverable — M3.
- [x] Persisted Silver, shadow comparison, and controlled Gold cutover exist —
  M4/M5.
- [x] Runtime observability, dbt semantic contracts, historical version
  migration, and reproducible deployment are verified — O1/S1/S1.1/H1.
- [x] Legacy outbox handoff is classified, recovered, and cleaned without
  touching data files — S1.2A–S1.2B.

### Active

- [ ] Run a controlled B2 canary against the 255 legitimate post-migration
  outbox manifests with legacy Gold and shadow comparison enabled.
- [ ] Pass the M5 cutover gate before switching Gold to persisted Silver.
- [ ] Collect representative B2 telemetry and make the evidence-based D-3a /
  O2 / no-change decision.

### Out of Scope

- Physical D-3a layout tuning until O1 telemetry demonstrates amplification.
- O2 tracing unless O1 diagnostics are insufficient.
- Multi-writer coordination and a new orchestration engine.
- F-305, F-306, F-709, and F-308 residual cleanup during the rollout phase.

## Context

The architecture remediation chain M1–M5, R1/R2, O1, S1, S1.1, H1, and
S1.2A–S1.2B is complete and verified. Baseline revision `89953fe` contains
the approved cleanup state: 140 stale outbox markers removed, 255 legitimate
post-migration manifests remaining, no in-flight or blocked work, Bronze and
Silver at 218,961 rows, zero NULL business versions, Silver equal to the
accepted B2 projection, and dbt 26/26 passing.

The current runtime remains:

```text
SILVER_MODE=legacy
GOLD_SOURCE=legacy
SHADOW_COMPARE=0
```

The next technical change is therefore a controlled rollout, not another
architecture investigation.

## Constraints

- **Correctness**: `business_version` is the only business ordering field;
  Kafka offsets never become business ordering authority.
- **Ownership**: PyIceberg owns B2 Silver; Gold remains legacy until the M5
  gate authorizes persisted-Silver cutover.
- **Safety**: Canary failure restores legacy Silver/Gold configuration and
  does not expose an unverified B2 result to Gold.
- **Evidence**: Every transition requires executable M5/O1 evidence; D-3a is
  telemetry-triggered.
- **Reproducibility**: Runtime versions and clean-stack behavior remain pinned
  as verified by H1.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| PyIceberg owns B2 Silver | Avoids the failed Trino position-delete interop contract | ✓ Good |
| Gold cutover follows M5 evidence | Keeps business-facing output on the known path during canary | — Pending |
| D-3a is telemetry-triggered | Synthetic SPIKE-2 alone cannot establish production cost | — Pending |
| Historical handoff cleanup deletes markers only | Bronze/Silver/parquet state is authoritative and preserved | ✓ Good |

---
*Last updated: 2026-08-09 after S1.2B verified cleanup and GSD re-baseline*
