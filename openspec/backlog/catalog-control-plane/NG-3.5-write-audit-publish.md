# NG-3.5 — Iceberg write-audit-publish

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `add-iceberg-write-audit-publish`
> **Authorization:** NONE

## Objective

Add a bounded write-audit-publish workflow so candidate Iceberg changes can be validated before becoming the published state consumed downstream.

## Depends on

NG-3.4 is a hard dependency because WAP acceptance must build on explicit, tested snapshot and rollback semantics rather than assume them.

## Scope

The implementation SHALL demonstrate a candidate-write lifecycle equivalent to:

```text
write candidate
      |
      v
auditable staged/candidate state
      |
      v
quality / contract validation
   |             |
 FAIL           PASS
   |             |
reject       publish
```

The exact mechanism MAY use Iceberg snapshot references, engine-supported WAP controls, or another standards-compatible approach supported by the pinned stack. The design SHALL prefer the smallest mechanism that proves the behavior without introducing a versioned catalog solely for feature breadth.

## Non-goals

- Adopting Nessie just to obtain Git-like branches/tags.
- Multi-table transactions.
- Replacing the existing B2 shadow/cutover model globally.
- A generic CI/CD framework for all data products.
- Human approval UI.

## Requirements

### Requirement: Candidate data is distinguishable from published data

Before publication, downstream readers using the normal published path SHALL not observe a candidate state that has not passed its audit gate.

### Requirement: Audit failure does not publish

A deliberately invalid candidate SHALL fail validation and the previously published table state SHALL remain the normal reader-visible state.

### Requirement: Successful audit publishes a known state

A valid candidate SHALL publish exactly the audited state, with snapshot/provenance evidence linking candidate, validation result and resulting published snapshot.

### Requirement: Rejection is recoverable

Rejecting a candidate SHALL not require manual object-store cleanup to restore correctness. Any cleanup of unreachable candidate artifacts SHALL be handled by normal Iceberg maintenance rules or a documented safe cleanup step.

### Requirement: WAP is observable

The workflow SHALL record bounded operational evidence for candidate creation, validation outcome and publication without promoting snapshot ids or other high-cardinality identities to Prometheus labels.

## Acceptance evidence

The archived change SHALL include:

- one failed candidate that is proven invisible on the normal published read path;
- one successful candidate whose audited contents match the published snapshot;
- snapshot/provenance receipts for both paths;
- recovery evidence after an interrupted candidate or publication attempt;
- confirmation that normal Iceberg maintenance still behaves safely with candidate artifacts.

## Rollback

The WAP path SHALL be feature-gated or otherwise reversible so the existing direct publication path can be restored without rewriting existing table history. Rollback SHALL identify and safely handle any staged but unpublished state.

## Hard stops

Stop if:

- the configured stack cannot distinguish candidate and published state reliably;
- the design requires adding a new catalog solely to mimic Git branches without a demonstrated need;
- a failed audit can become reader-visible;
- recovery from an interrupted publish cannot be made deterministic.

## Freshness of external assumptions

WAP support differs across Iceberg engines/catalogs and versions. Reverify the repository's pinned PyIceberg/Trino/catalog capabilities and current Iceberg guidance at promotion before selecting the mechanism.
