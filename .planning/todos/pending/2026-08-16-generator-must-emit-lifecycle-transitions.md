---
created: 2026-08-16T17:40:00.000Z
title: Generator must emit lifecycle transitions (ADR-0001 D-1, consequence 2)
area: domain
priority: medium (implementation drift on an accepted decision, not a new decision)
files:
  - kafka/producer/orders_producer.py
  - tests/e2e/test_lakehouse_e2e.py
  - docs/CONFIGURATION.md
---

## Problem

This is **implementation drift on an accepted decision**, not an open question.
D-1 is not to be re-litigated here.

**Accepted decision** — [ADR-0001 D-1](../../../docs/adr/0001-incremental-silver-and-gold.md):
an order is a mutable business entity, and lifecycle transitions are part of the
domain model. D-1 listed three consequences. Two shipped:

- ✅ `business_version` added to the event contract and all four schema declarations
  (`orders_streaming.py`, `iceberg_writer.py`, `iceberg_medallion.py`, `marts.streaming_orders`)
- ✅ the E2E fixture carries explicit versions (`tests/e2e/test_lakehouse_e2e.py` — v1, v5, v3)
- ❌ **consequence 2 — "The generator must emit lifecycle transitions — reusing
  `order_id` across events and incrementing `business_version`" — never implemented**

**Current drift**: `create_event()` emits a fresh `uuid.uuid4()` as `order_id` with
`business_version` hardcoded to `1` (`kafka/producer/orders_producer.py:105,111`).
Nothing in `kafka/` or `spark/` ever emits or increments past version 1, so the live
workload can never produce a second version of an order. Every branch of D-1a's
resolution table except the first is unreachable from running data — the version
resolution machinery is exercised only by tests and fixtures.

The producer's status is settled and is **not** a reason to revisit the domain model:
ADR-0001 classifies it as *"Incidental. The only artifact modelling immutable
entities, and the cheapest of the four to change"* and states *"the weakest candidate
for the source of domain truth is the generator"*. Its own comment distinguishes the
"historical demo producer" from a "new-baseline deployment". It is a demo workload
generator, explicitly non-normative.

## Solution

**Required outcome**: the generator sometimes reuses an existing `order_id` with a
monotonically increasing `business_version`.

**Non-goal**: redefining Silver conflict-resolution semantics. D-1 and D-1a stand as
written; this todo changes one artifact to match them.

**Acceptance**: a running workload demonstrates at least one `v1 → v2` transition
reaching Silver through the normal Kafka → Spark → landing → Bronze path.

### Why this is its own branch/PR

This is not "making the demo more realistic". It is the first change to the
*reachable state space* of the running stack:

```text
today:                  after:
new UUID / v1           order A / v1
new UUID / v1           order B / v1
new UUID / v1           order A / v2
```

Behaviour that has never executed on the live path starts executing regularly:
replacement of an older business version, stale-version rejection, shadow comparison
paths, FF-14-related behaviour, and Gold recomputation after an order mutates.

### Phases

1. **Make lifecycle updates safe to generate.** A small bounded state store in the
   demo producer: known order IDs plus their current version. Update probability
   controlled by an env var, with the **default preserving today's behaviour**
   (e.g. `ORDER_UPDATE_PROBABILITY=0`), and an explicit non-zero value set in the
   extended/demo stack.
2. **Prove the live path.** A deterministic integration scenario that publishes `v1`
   then `v2` for one `order_id` and asserts the Silver/Gold result. Do not rely on
   the random producer probability for proof.
3. **Exercise conflicts deliberately, not accidentally.** Keep these three distinct:

   ```text
   normal lifecycle:   A/v1 → A/v2 → A/v3        generator MUST do this (D-1)
   stale/replay:       A/v3 → A/v2                useful to reproduce
   domain conflict:    A/v3(payload X) + A/v3(payload Y)   fault injection only
   ```

   Same `order_id` + same `business_version` + different payload is a data-quality
   violation under D-1a and must not arise from ordinary demo load. Confine it to a
   dedicated test/workload mode.
