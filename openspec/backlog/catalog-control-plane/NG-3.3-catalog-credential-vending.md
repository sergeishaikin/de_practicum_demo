# NG-3.3 — Scoped credential vending

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `add-catalog-credential-vending`
> **Authorization:** NONE

## Objective

Replace broad, long-lived storage access on the catalog-mediated lakehouse path with short-lived, least-privilege credentials or an equivalent bounded signing mechanism issued after authorization.

## Depends on

NG-3.2 is a hard dependency because credential scope must be derived from an enforced principal/action/resource decision rather than from static service identity alone.

## Baseline gap

The current Trino configuration is generated from MinIO credentials supplied through environment variables. Secrets are not hard-coded, but the model is still broader and longer-lived than the credential-vending pattern described in the metastore analysis.

## Scope

The implementation SHALL demonstrate:

- temporary credentials, remote request signing, or an equivalent mechanism supported by the selected catalog/storage stack;
- scope bounded to the resource and operation class required by the authorized request;
- expiry/rotation behavior;
- failure after expiry or revocation;
- no catalog proxying of data bytes;
- direct Trino/PyIceberg access to MinIO after control-plane authorization.

## Non-goals

- Production cloud IAM parity.
- Permanent root/admin credentials distributed to compute engines.
- Replacing MinIO purely to obtain a cloud-specific STS implementation unless the selected design proves no equivalent local demonstration is possible.
- Credential vending for unrelated PostgreSQL/Kafka services.

## Requirements

### Requirement: Issued credentials are short-lived

The issued access material SHALL expire automatically and the acceptance test SHALL prove that previously valid access no longer succeeds after the bounded lifetime or explicit revocation condition.

### Requirement: Issued credentials are scoped

A credential issued for one allowed warehouse/table scope SHALL NOT grant unrestricted write/admin access to the entire object store.

### Requirement: Authorization precedes issuance

A denied principal/action/resource request SHALL NOT receive usable storage credentials.

### Requirement: The catalog stays off the data path

Credential issuance or signing SHALL not turn the catalog into a proxy for Parquet/Iceberg data transfer.

### Requirement: Credential events are auditable but secret-safe

Issuance, denial, expiry and revocation MAY be audited by identifier/scope metadata, but raw secret values SHALL never be emitted to logs, traces, metrics or audit records.

## Acceptance evidence

The archived change SHALL include:

- an architecture diagram showing control-plane issuance and direct data-plane access;
- a successful authorized read/write using temporary scoped access;
- a denied out-of-scope operation;
- an expiry or revocation test;
- proof that no permanent broad credential was added to application configuration;
- secret-scanning/log-inspection evidence for the new path;
- applicable live Iceberg/Trino integration evidence.

## Rollback

Rollback SHALL restore the previous environment-driven local credential path without changing Iceberg table contents. The rollback route is for local recovery only and SHALL not be represented as equivalent security.

## Hard stops

Stop if:

- the proposed mechanism only renames a permanent broad secret rather than bounding lifetime/scope;
- the selected catalog/storage combination cannot issue or sign bounded access and the design would fake vending at application level;
- direct object-store access would have to be replaced by catalog data proxying;
- secret material appears in telemetry or committed configuration.

## Freshness of external assumptions

Credential vending, STS, remote signing and MinIO/S3 compatibility are time-sensitive product capabilities. Reverify the selected catalog and storage documentation at promotion and record the exact supported mechanism/version before implementation.
