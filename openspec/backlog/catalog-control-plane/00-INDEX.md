# Catalog Control Plane — Gap Programme

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This package records planned work only; it does not authorize implementation.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `main`
> **Baseline date:** 2026-09-06

## Purpose

This programme converts the metastore/catalog gap analysis into a bounded set of OpenSpec backlog items for the current Iceberg-first platform.

The baseline already has the architecture the SmartData metastore talk argues for: storage/compute separation, MinIO object storage, Iceberg tables, an Iceberg REST catalog, PyIceberg and Trino sharing that catalog, OpenMetadata/OpenLineage governance, and Airflow-driven Iceberg maintenance. The programme therefore does **not** replace the working lakehouse. It targets the missing control-plane depth: catalog authorization, scoped credentials, explicit Iceberg semantic demonstrations, write-audit-publish, and the documented Kafka-to-landing lineage gap.

A product is added only when it closes one of those gaps. Hive Metastore, AWS Glue, Unity Catalog, Nessie, ML-model registry, catalog volumes, catalog HA, and a custom metastore are not programme objectives.

## Backlog register

| Item | File | Gate | Depends on | Change | State | Disposition | Authorised by | At |
|---|---|---|---|---|---|---|---|---|
| NG-3.1 | `NG-3.1-catalog-control-plane-evaluation.md` | EXPERIMENT | - | `evaluate-catalog-control-plane` | PLANNED | pending | `none` | - |
| NG-3.2 | `NG-3.2-catalog-authorization-rbac.md` | ADOPT | NG-3.1 | `add-catalog-authorization-rbac` | PLANNED | pending | `none` | - |
| NG-3.3 | `NG-3.3-catalog-credential-vending.md` | ADOPT | NG-3.2 | `add-catalog-credential-vending` | PLANNED | pending | `none` | - |
| NG-3.4 | `NG-3.4-iceberg-semantics-contract.md` | ADOPT | - | `prove-iceberg-semantics` | PLANNED | pending | `none` | - |
| NG-3.5 | `NG-3.5-write-audit-publish.md` | ADOPT | NG-3.4 | `add-iceberg-write-audit-publish` | PLANNED | pending | `none` | - |
| NG-3.6 | `NG-3.6-kafka-landing-lineage.md` | ADOPT | - | `close-kafka-landing-lineage-gap` | PLANNED | pending | `none` | - |

Row order is a valid technical dependency order. It is not an authorization chain. Completing one item only makes a dependent item eligible to be authorised.

## Why these six items

The metastore talk covers a much wider surface than this repository needs. This programme keeps only capabilities that materially improve the existing demo.

- **NG-3.1** prevents a premature implementation choice. The current REST catalog is kept unless evidence shows it cannot support the required control plane cleanly. Apache Polaris is evaluated as the leading modern alternative; Nessie is considered only if branching/WAP semantics require it.
- **NG-3.2** adds the missing authorization plane: identities, roles, privileges, decisions, and an auditable allow/deny trail.
- **NG-3.3** replaces broad long-lived storage credentials on the catalog-mediated path with short-lived scoped credentials or an equivalent bounded mechanism supported by the selected catalog/storage combination.
- **NG-3.4** proves the Iceberg capabilities the platform currently relies on but does not prominently demonstrate: schema evolution, partition evolution, snapshots/time travel, rollback, and concurrent commit behavior.
- **NG-3.5** adds a bounded write-audit-publish flow instead of adding Git-like data branches merely for feature breadth.
- **NG-3.6** closes the existing documented runtime-lineage gap from Kafka to landing so lineage is end to end from source boundary to Gold.

## Explicit non-goals from the gap analysis

The following were considered and are deliberately outside this programme unless a later, separately authorised spec proves a concrete gap:

- writing a custom metastore/catalog service;
- adding Hive Metastore to an Iceberg REST architecture;
- AWS Glue or Unity Catalog integration in the local cloud-neutral demo;
- adopting Nessie only to demonstrate Git-like branches/tags;
- multi-table transactions without a real atomic business operation;
- catalog-managed ML models or generic volumes/BLOBs;
- catalog federation or multi-catalog governance beyond existing Trino federation capability;
- catalog HA, Kubernetes deployment, or production-scale load engineering;
- a bespoke catalog UI when OpenMetadata already provides metadata discovery/UI;
- full enterprise IAM/SSO where a bounded local identity/RBAC model proves the architectural point.

## Cross-cutting invariants

1. **Iceberg remains canonical analytical truth.** No control-plane component may silently move ownership to PostgreSQL, OpenMetadata, or a new catalog backend.
2. **The catalog remains control plane, not data proxy.** Trino/PyIceberg continue to read/write MinIO directly after catalog coordination.
3. **OpenLineage remains the runtime-lineage protocol boundary.** Closing the Kafka-to-landing gap must not couple lineage semantics to OpenMetadata internals.
4. **Security changes fail closed for authorization and credential issuance, but metadata/telemetry outages must not corrupt committed data.**
5. **No permanent broad credentials are introduced as a workaround.** If short-lived vending is not feasible, the item records the limitation rather than claiming equivalent security.
6. **Existing recovery, snapshot provenance, idempotency, maintenance, and observability contracts are preserved.**
7. **New services stay optional unless they are required for the core data path and the decision is explicitly adopted.**
8. **External product assumptions are revalidated at promotion.** The 2026-09-06 comparison is planning context, not future authority.
9. **The programme does not authorise itself to grow.** Anything outside NG-3.1 … NG-3.6 requires a separate operator grant.

## Suggested execution sequence

Technical dependencies allow some parallelism, but the recommended sequence is:

```text
NG-3.1  catalog/control-plane evaluation
   |
NG-3.2  authorization + RBAC + audit
   |
NG-3.3  credential vending

NG-3.4  Iceberg semantics proof
   |
NG-3.5  WAP

NG-3.6  Kafka -> landing lineage
```

NG-3.4 and NG-3.6 can be done independently of the catalog-security chain. This is a recommendation only, not a grant.

## Promotion contract

For each item:

1. obtain explicit operator authorisation unless a separately recorded bounded programme authorisation covers it;
2. open exactly the change id named in the register;
3. re-read current `main`, standing specs, README, and relevant tests;
4. revalidate external product/version assumptions against primary documentation;
5. create `proposal.md`, `design.md`, `tasks.md`, and the required spec delta before implementation;
6. run the repository completion gate plus the item's live acceptance evidence;
7. archive the change and update this register only after the repository state proves the lifecycle transition;
8. stop unless the next item is separately authorised.

## Freshness of external assumptions

This package was derived on 2026-09-06 from the current repository and the contemporary Iceberg/REST-catalog ecosystem. Product maturity, REST-catalog capabilities, credential-vending support, Trino integration, and Polaris/Nessie behavior SHALL be reverified from primary documentation when any item is promoted.
