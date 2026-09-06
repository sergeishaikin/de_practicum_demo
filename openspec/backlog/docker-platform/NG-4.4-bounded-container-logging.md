# NG-4.4 — Bounded Docker runtime logging

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `bound-container-runtime-logs`
> **Authorization:** NONE

## Objective

Make local Docker logging disk usage bounded for every long-running service unless a measured exception proves another driver/storage contract already bounds it.

## Baseline gap

`docker-compose.extended.yml` defines `x-bounded-logging` using the `json-file` driver with `max-size: 50m` and `max-file: 3`, and several Spark/Iceberg services use it. The policy is not expressed uniformly across the core and extended Compose graphs; for example MinIO in the inspected configuration has no `logging: *bounded-logging` attachment. The existing comment correctly identifies restart loops as a Docker-VM disk-growth risk, but the repository lacks an exhaustive coverage contract.

## Scope

- inventory every long-running Compose service and its effective Docker logging driver/options;
- classify each service as bounded by the repository json-file policy, bounded by an equivalent mechanism, or explicitly exempt;
- apply a shared bounded policy where compatible;
- preserve stdout/stderr as the local fallback and preserve the existing OTLP/Loki first-party application logging path;
- add a machine-checkable coverage rule so newly added long-running services cannot silently omit a bound.

## Non-goals

- Replacing Loki/OTel with Docker logging drivers.
- Shipping all third-party container logs to Loki.
- Treating one-shot init/bootstrap jobs as long-running daemons when they have different retention risk.
- Selecting a production log platform.

## Requirements

### Requirement: Long-running Docker logs are bounded

Every long-running service SHALL have a finite Docker-log retention/rotation contract or an explicit evidence-backed exception.

### Requirement: Application observability remains independent

Bounding Docker engine logs SHALL NOT remove stdout fallback, change the adopted Loki/OTLP scope, or make Loki availability a prerequisite for business processing.

### Requirement: Coverage is machine-checkable

The repository SHALL have a non-vacuous fitness rule that enumerates the relevant service set and fails when a new long-running service lacks a bounded logging policy or declared equivalent.

### Requirement: Failure diagnostics remain sufficient

Rotation limits SHALL retain enough recent output for the repository's failure-collection workflows and local troubleshooting procedures.

## Acceptance evidence

The archived change SHALL include:

- exact before/after counts of long-running services by logging policy;
- a table of any retained exceptions and why they are bounded elsewhere;
- a synthetic or temporary restart-loop proof showing Docker log growth stops at the configured bound within expected tolerance;
- CI failure-log collection proof after the policy change;
- a non-vacuous architecture test that detects an intentionally unbounded service;
- confirmation that Loki/OTel and stdout behavior remain unchanged for in-scope first-party services.

## Rollback

The shared Docker logging policy SHALL be revertible without changing application log schemas, persisted data or observability backends.

## Hard stops

Stop if a logging-driver change prevents required CI log capture, hides startup failures, or is being used to broaden Loki scope without the separate capability authorization that would require.

## Freshness of external assumptions

Reverify Docker logging-driver options at promotion and re-inventory every Compose service from current `main`.