# NG-4.2 — Runtime secret containment

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `contain-runtime-secrets`
> **Authorization:** NONE

## Objective

Reduce broad environment-variable exposure of runtime credentials by moving supported services to file-mounted Compose secrets or an equivalently bounded local mechanism, without introducing a heavyweight secret-management product solely for the demo.

## Baseline gap

`.env.example` contains at least fourteen password/secret-style values spanning PostgreSQL, Airflow, MinIO, Grafana, Superset, Tempo, Loki and OpenMetadata. `.env` is excluded from the Docker build context and values are not hard-coded into images, but runtime delivery is predominantly through Compose `environment:` entries.

## Scope

- inventory every runtime secret, its producer, consumer and current delivery path;
- classify each consumer by native `_FILE`/file-secret support, wrapper-adaptation feasibility, or justified environment-only exception;
- migrate the feasible high-value paths to Compose secrets or an equivalent local file-mounted mechanism;
- ensure secret files are mounted only into services that consume them;
- prevent raw secret values from logs, traces, metrics, generated config artifacts and acceptance evidence;
- add a regression check for accidental hard-coded or unnecessarily broad secret propagation.

## Non-goals

- Vault, cloud KMS or enterprise IAM purely for breadth.
- Rotating every local demo credential on a production cadence.
- Credential vending for Iceberg object-store access; that is owned by the catalog-control-plane programme if adopted.
- Treating public/non-sensitive configuration as secrets.

## Requirements

### Requirement: Secret scope is explicit

Each runtime secret SHALL have a documented set of consuming services. A secret SHALL NOT be mounted or injected into unrelated services for convenience.

### Requirement: File delivery is preferred where supported

When the pinned service or a small first-party wrapper supports file-based secret ingestion, the runtime SHALL prefer that mechanism over ordinary environment-variable delivery.

### Requirement: Unsupported consumers are recorded, not disguised

A service that cannot safely consume a file-mounted secret MAY retain environment delivery only with a documented reason, bounded scope and regression evidence that the value does not persist into repository artifacts or telemetry.

### Requirement: Acceptance evidence is secret-safe

Tests and evidence SHALL identify secret names and delivery mechanisms only. Raw values SHALL NOT be committed, printed or uploaded as artifacts.

## Acceptance evidence

The archived change SHALL include:

- a before/after secret inventory with exact counts by delivery mechanism;
- per-service compatibility evidence for every migrated or retained secret path;
- `docker compose config`/container inspection proving intended secret mounts without exposing values in the receipt;
- negative scans over repository, logs and generated artifacts for seeded canary secret values;
- a live stack proof that migrated services start and perform their existing workloads;
- a non-vacuous regression test that detects an intentionally injected forbidden secret exposure.

## Rollback

Each migrated service SHALL have a documented rollback to its prior local environment-based mechanism without changing data formats or deleting persistent state. Rollback is recovery behavior, not equivalent security.

## Hard stops

Stop if a migration requires copying a secret into an image layer, widening secret scope, committing generated credentials, or introducing a new secret-management service whose operational surface exceeds the bounded local benefit.

## Freshness of external assumptions

Reverify current Compose secret semantics and each pinned image's file-secret support at promotion. Remeasure the secret inventory from current `main`.