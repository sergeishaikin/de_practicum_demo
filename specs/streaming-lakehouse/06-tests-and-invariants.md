# Layer 6 — Tests and Invariants

This layer translates the AS-IS behavior into properties that should remain true under refactoring.

## Ingestion invariants

1. A landing Parquet object that is not present in Spark committed sink metadata must not be ingested into Bronze.
2. A landing file already marked done must not be appended again.
3. A `load_id` already present in Bronze snapshot metadata must not create another Bronze append after restart.
4. Bronze schema evolution for the canonical lineage baseline is additive and must preserve compatibility with historical landing files.
5. Bronze remains partitioned by day of `event_date`.

## Outbox/recovery invariants

1. Downstream work is published only for a committed Bronze load.
2. Recovery must be able to reconcile local pending state against durable Iceberg commit state.
3. Duplicate/ambiguous durable completion identity must not be silently accepted.
4. Failure to persist optional shadow certification may cause repeated comparison, but must not bypass comparison.
5. Corrupt, unreadable or incompatible shadow certification must behave as absent certification.

## Medallion invariants

1. Silver contains at most the winning business state for an `order_id` according to business-version ordering semantics.
2. Kafka offset is transport metadata, not the authority for business-version ordering.
3. Gold grain is `(event_date, country, status)`.
4. Gold metrics expose order count, total amount, average amount and distinct customer count.
5. Unsupported rollout configuration fails validation.
6. `b2 + persisted_silver + shadow=0` is not a valid runtime state.
7. When Gold provenance names the current persisted Silver snapshot, a redundant Gold rebuild may be skipped.

## Lineage invariants

1. `landing -> bronze` may be emitted by the writer because that service performs the edge.
2. `bronze -> silver` and `silver -> gold` may be emitted by medallion processing.
3. The writer must not claim `Kafka -> landing`, because it does not perform that edge.

## Suggested verification map

```text
Invariant                       Verification target
------------------------------  -------------------------------------------
Spark commit authority          writer unit/integration tests
Bronze load idempotency         crash-before/after-commit integration tests
Outbox publication              writer integration tests
Completion receipt semantics    medallion recovery tests
Shadow fail-safe behavior       medallion shadow tests
Rollout tuple validation        cutover unit tests
Silver dedup business rule      medallion data tests
Gold aggregate grain            medallion data tests
Lineage edge ownership          lineage tests/docs validation
```

## Acceptance criterion for this Layered Spec

A reviewer who has not read the implementation should be able to answer all of the following from these six layers:

- Where does Spark stop and PyIceberg begin?
- What makes a landing file eligible for Bronze ingestion?
- How is duplicate Bronze append prevented after a crash?
- Which durable artifacts carry downstream progress/correctness evidence?
- What is the business ordering field for Silver deduplication?
- What are the four medallion rollout states and which one is the shipped default?
- Under what condition can Gold use persisted Silver as its source?
- Which lineage edges are emitted and which edge is intentionally absent?

If those questions cannot be answered, the spec is not yet an adequate behavioral representation of the codebase.