# NG-3.1 — Catalog control-plane evaluation

> **Lifecycle:** PLANNED
> **Gate:** EXPERIMENT
> **Change:** `evaluate-catalog-control-plane`
> **Authorization:** NONE

## Objective

Determine whether the current Iceberg REST catalog can remain the platform's catalog while supporting the security/control-plane capabilities required by NG-3.2 and NG-3.3, or whether a compatible replacement such as Apache Polaris is justified.

## Baseline gap

The repository already uses an Iceberg REST catalog correctly as a metadata/control-plane boundary, but it does not demonstrate catalog-level RBAC, authorization decisions, access audit, or scoped credential vending. The experiment SHALL distinguish a product capability gap from a configuration/integration gap before any catalog replacement is proposed.

## Scope

The change SHALL evaluate the current catalog and at least one modern Iceberg REST Catalog implementation against these requirements:

- Iceberg REST interoperability with Trino and PyIceberg used by this repository;
- namespaces/tables and current-metadata commit coordination;
- RBAC or an equivalent external authorization integration;
- auditable allow/deny decisions;
- short-lived scoped storage credentials, remote signing, or an equivalent bounded access mechanism;
- MinIO/S3-compatible storage support appropriate to the local demo;
- deployability within the repository's optional-profile resource budget;
- operational observability and clear failure behavior;
- migration/rollback without rewriting Iceberg data files.

Apache Polaris SHALL be evaluated unless primary documentation at promotion proves it is no longer a relevant Iceberg REST option. Nessie MAY be evaluated only if a requirement cannot be answered without its versioned-catalog semantics.

## Non-goals

- No production catalog replacement during this experiment.
- No custom metastore implementation.
- No Hive Metastore, Glue, or Unity Catalog adoption merely for comparison breadth.
- No WAP implementation; NG-3.5 owns that capability.
- No security claim based only on a product feature list.

## Requirements

### Requirement: The decision is evidence-based

The change SHALL record a capability matrix backed by primary documentation and a minimal live compatibility proof for every candidate that survives the paper gate.

### Requirement: The existing catalog wins by default

The current catalog SHALL remain selected unless another option closes a required gap that cannot be closed cleanly in the existing architecture and the benefit exceeds migration/resource cost.

### Requirement: REST remains the interoperability boundary

Any adopted backend SHALL preserve an Iceberg REST-compatible boundary for Trino/PyIceberg rather than introducing engine-specific catalog coupling.

### Requirement: Data files are not migrated to prove catalog choice

The evaluation SHALL prove that the selected migration path can preserve existing Iceberg table data/metadata ownership and SHALL NOT rewrite warehouse data merely to change the catalog service.

## Acceptance evidence

The archived change SHALL contain:

- a dated feature/capability matrix with source links;
- exact candidate versions and container/resource measurements;
- a live smoke proving Trino and PyIceberg can resolve and query the same test Iceberg table through each surviving candidate, where feasible;
- an explicit decision: `KEEP_CURRENT`, `ADOPT_POLARIS`, or another named REST-compatible outcome;
- a migration and rollback sketch for any non-current outcome;
- a list of requirements that remain intentionally deferred.

## Rollback

This is an evaluation-only change. Rollback is removal of temporary candidate services/configuration and restoration of the pre-experiment stack. Existing catalog state and warehouse data SHALL remain untouched.

## Hard stops

Stop before implementation if:

- the current repository behavior contradicts the baseline assumptions above;
- a candidate requires destructive metadata/data migration to evaluate;
- primary documentation cannot establish supported Trino/PyIceberg/MinIO behavior;
- the evaluation would require introducing permanent credentials or weakening existing tests.

## Freshness of external assumptions

Catalog products and REST integrations evolve quickly. Versions, security features, credential-vending behavior, Trino/PyIceberg compatibility, and deployment requirements SHALL be reverified from primary documentation when this item is promoted. Nothing captured on 2026-09-06 is authority for a later implementation decision.
