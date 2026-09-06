# NG-3.2 — Catalog authorization, RBAC and access audit

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `add-catalog-authorization-rbac`
> **Authorization:** NONE

## Objective

Add a bounded security plane around catalog operations so that access decisions are explicit, role-based and auditable instead of relying only on service-level storage credentials.

## Depends on

NG-3.1 is a hard dependency because this item must implement against the selected catalog/control-plane architecture rather than assume one prematurely.

## Scope

The implementation SHALL introduce a minimal local identity/authorization model sufficient to demonstrate the control-plane behavior from the metastore analysis:

- principals with stable identities;
- roles and explicit privileges;
- authorization decisions on catalog/table operations;
- deny-by-default behavior for operations not granted;
- an auditable decision record containing principal, action, resource, decision and timestamp;
- a clear separation between authorization audit and ordinary observability telemetry.

At minimum the demo SHALL support equivalent roles to:

- `data_reader` — read approved analytical tables;
- `data_engineer` — read/write the governed lakehouse scope needed by ingestion/medallion jobs;
- `platform_admin` — catalog administration.

Exact names MAY differ if the design establishes a better mapping to the selected catalog.

## Non-goals

- Full enterprise SSO, SCIM, LDAP or organization-wide IAM.
- Row-level or column-level security unless required to prove the selected authorization integration; FGAC is not a completion criterion for this item.
- Building a custom policy engine when the selected catalog has a sufficient native or external-policy integration.
- Replacing OpenMetadata as the metadata-discovery UI.

## Requirements

### Requirement: Authorization is enforced before privileged catalog operations

A caller without the required privilege SHALL be denied before the protected operation is accepted.

### Requirement: Deny decisions are observable as security audit

Every governed authorization decision SHALL produce a bounded audit record that identifies the decision without leaking credentials or row payloads.

### Requirement: Audit is distinct from telemetry

Prometheus/OTel/Loki MAY carry operational signals about authorization, but the security decision record SHALL have a defined retention/query path and SHALL NOT be inferred from generic application logs alone.

### Requirement: Roles are least-privilege demonstrations

The default demo identities SHALL not all share administrator-equivalent rights. At least one negative test SHALL prove a reader cannot perform a write/admin action.

### Requirement: Existing data-path semantics are preserved

Adding authorization SHALL NOT change Iceberg ownership, snapshot semantics, medallion logic, Kafka recovery semantics or maintenance behavior except where access is deliberately denied by the new policy.

## Acceptance evidence

The archived change SHALL include:

- the role/privilege matrix;
- positive and negative authorization tests;
- a live proof showing an allowed read, a denied write, and an allowed administrative action by appropriate principals;
- captured audit records for both allow and deny decisions;
- evidence that no secret or data payload is emitted in those records;
- applicable fast, integration and clean-stack gates.

## Rollback

The security layer SHALL be removable or disableable through documented configuration so the prior local catalog path can be restored without rewriting Iceberg tables. Rollback SHALL NOT require deleting MinIO warehouse data.

## Hard stops

Stop if:

- the selected catalog cannot enforce the intended decision at the catalog boundary and the design would merely log unenforced policy;
- implementation requires distributing administrator credentials to all compute clients;
- a proposed audit path leaks secrets or user data;
- authorization breaks existing recovery/maintenance behavior without an explicit spec decision.

## Freshness of external assumptions

Authorization features, privilege vocabularies and policy integrations of the selected catalog SHALL be reverified from primary documentation at promotion. The design SHALL not carry feature names or limitations from the 2026-09-06 analysis without rechecking them.
