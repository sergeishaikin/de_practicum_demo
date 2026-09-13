# Streaming Lakehouse — Layered Spec (AS-IS)

This directory reverse-engineers the existing streaming lakehouse from the implementation on `main`.

It is intentionally descriptive, not aspirational: every rule should be traceable to code, configuration, or tests. Proposed changes belong elsewhere (for example OpenSpec), then this AS-IS model can be regenerated or promoted to a TO-BE model after review.

## Scope

The first slice covers the runtime path:

`Kafka -> Spark Structured Streaming -> MinIO landing -> PyIceberg writer -> bronze.orders -> medallion -> silver.orders_clean -> gold.orders_daily_metrics -> Trino`

It also captures the non-obvious semantics that matter for correctness: Spark commit authority, writer idempotency/recovery, Bronze outbox publication, medallion progress/completion receipts, shadow certification, and rollout modes.

## Layers

1. [01-workflow.md](01-workflow.md) — system workflow and boundaries
2. [02-data-contracts.md](02-data-contracts.md) — Bronze/Silver/Gold contracts
3. [03-behavior.md](03-behavior.md) — operational behavior and processing rules
4. [04-state-and-recovery.md](04-state-and-recovery.md) — idempotency, recovery, durable state
5. [05-medallion-rollout.md](05-medallion-rollout.md) — legacy/B2 rollout state machine
6. [06-tests-and-invariants.md](06-tests-and-invariants.md) — invariants and validation targets

## Source-of-truth rule

If this spec disagrees with implementation, implementation wins until the discrepancy is reviewed. The purpose of the spec is to make those discrepancies visible, not to hide them.