# NG-3.4 — Iceberg semantics contract

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `prove-iceberg-semantics`
> **Authorization:** NONE

## Objective

Turn Iceberg's important table-format properties from implicit platform capability into explicit, executable portfolio evidence.

## Scope

The change SHALL add deterministic demonstrations and tests for the Iceberg behaviors most relevant to this repository:

- schema evolution that preserves readable historical data;
- partition evolution without rewriting all historical data merely to change the partition spec;
- snapshot inspection and time travel;
- rollback or equivalent restoration to a prior valid table state;
- concurrent/competing commit behavior showing that stale writers do not silently overwrite a newer table state.

The tests SHALL use the repository's existing REST catalog and MinIO path unless NG-3.1 has already adopted a compatible replacement.

## Non-goals

- Benchmarking every Iceberg feature.
- Testing vendor-specific extensions unrelated to the repository.
- Claiming multi-table ACID semantics.
- Replacing the medallion design.
- Adding a second table format for comparison.

## Requirements

### Requirement: Every claimed Iceberg property has executable evidence

README/docs SHALL not claim a semantic property solely because Iceberg supports it in theory. Each property named in this item SHALL have a focused test or live acceptance scenario against the configured stack.

### Requirement: Evolution preserves existing data contracts

Schema and partition evolution tests SHALL prove both the new state and continued readability/interpretability of pre-evolution data.

### Requirement: Historical snapshots are queryable

At least one test SHALL identify a concrete prior snapshot and prove a query against historical state returns the expected earlier result.

### Requirement: Rollback is explicit and verified

A rollback scenario SHALL demonstrate the table's current state changing back to a selected valid historical state without manually rewriting data files.

### Requirement: Conflicting commits do not become silent lost updates

A competing-writer test SHALL prove the configured catalog/table semantics reject, retry, or otherwise safely resolve a stale commit rather than silently replacing a newer committed state.

## Acceptance evidence

The archived change SHALL include:

- focused fast tests where possible and live Iceberg/Trino integration evidence where required;
- before/after schemas and partition specs;
- snapshot identifiers used for time travel and rollback;
- the observed competing-commit result and why it is safe;
- documentation explaining what Parquet provides versus what Iceberg provides versus what the catalog coordinates.

## Rollback

Tests SHALL use isolated namespaces/tables or disposable fixtures. No acceptance scenario may mutate the persistent demo's canonical sample tables without an explicit restoration step and evidence that restoration succeeded.

## Hard stops

Stop if:

- a test would need to fabricate behavior unsupported by the configured engine/catalog combination;
- rollback or concurrency evidence cannot be made deterministic enough to distinguish a real semantic guarantee from timing luck;
- implementing the test requires weakening existing snapshot/recovery contracts.

## Freshness of external assumptions

Iceberg, PyIceberg and Trino behavior/version support SHALL be revalidated at promotion. The semantic contract SHALL be written from the behavior of the repository's pinned versions, not from a generic feature list.
