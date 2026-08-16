---
title: Evaluate Airflow-owned medallion processing
trigger_condition: Project Phase 2 is implemented, live-verified, and stable with exact Asset provenance and no business-semantic regression
planted_date: 2026-08-16
status: seed
---

# Airflow-Owned Medallion Evaluation

## Status

This is a future evaluation seed, not an approved requirement, roadmap phase,
or current-scope commitment.

## Question

After the warehouse Asset boundary has proven reliable, determine whether
there is real operational value in moving Bronze-to-Silver-to-Gold medallion
orchestration from the long-running `iceberg-medallion` service into an
Asset-driven Airflow DAG.

## Trigger conditions

Evaluate only after project Phase 2 demonstrates:

- successful manual ingestion to Asset-triggered downstream operation;
- exact source/downstream DagRun provenance;
- no duplicate or missing Asset-triggered runs;
- unchanged warehouse business results and recovery behavior;
- stable operation through failure and rerun scenarios.

## Questions for the future spike

- What event authoritatively represents a committed Bronze update?
- Can Airflow own discrete medallion work without weakening the current B2
  completion ledger, shadow comparison, or crash recovery?
- How are streaming cadence, backpressure, and multiple Bronze updates
  coalesced without missed or duplicate processing?
- What rollback restores the current `iceberg-medallion` service ownership?
- Does the UI/operational benefit justify the migration risk?

## Explicit non-authorization

Do not stop or replace `iceberg-medallion`, change its cycle, emit new
Bronze/Silver/Gold Assets, or modify streaming/recovery ownership based on this
seed alone. A separate spike, requirements decision, and approved phase are
required.
