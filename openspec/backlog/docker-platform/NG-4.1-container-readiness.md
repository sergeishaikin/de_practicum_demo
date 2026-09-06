# NG-4.1 — Container readiness contract

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `harden-container-readiness`
> **Authorization:** NONE

## Objective

Make Compose startup dependencies express when an upstream service is actually usable by its consumer rather than merely when its container process has started.

## Baseline gap

The repository already contains good readiness examples: PostgreSQL is probed over TCP because dependants use TCP; Kafka executes a broker command; Spark Connect and Iceberg REST have explicit health checks. The inspected extended graph still contains at least nine `service_started` edges, and MinIO has no health check despite being a startup dependency of Spark, Jupyter, Iceberg REST and the Iceberg writer.

The change SHALL begin by re-counting all `depends_on` edges and health checks from current Compose files. The 2026-09-06 count is a planning baseline, not acceptance evidence.

## Scope

- inventory every Compose dependency edge and classify it as `started`, `healthy`, one-shot completion, or intentionally retry-tolerant;
- add meaningful readiness probes where a dependant requires upstream usability;
- prefer `service_healthy` or `service_completed_successfully` only where the probe represents the path the dependant actually consumes;
- preserve application-level retry/recovery where that is the correct distributed-systems contract;
- add a machine-checkable fitness rule preventing newly introduced readiness regressions.

## Non-goals

- Turning every service into a health-checked service regardless of dependency semantics.
- Replacing application retries with Compose ordering.
- Kubernetes-style liveness/readiness infrastructure.
- Changing business processing logic merely to make Compose pass.

## Requirements

### Requirement: Startup dependencies describe usable state

When service B cannot function until service A is usable, B SHALL NOT depend only on `service_started` for A.

### Requirement: Probes exercise the consumed boundary

A health check SHALL exercise the same protocol or a justified equivalent boundary used by dependants. A PID-only or socket-only check is insufficient when it can report healthy before the required service operation succeeds.

### Requirement: Retry-tolerant dependencies are explicit

If a consumer is intentionally allowed to start before its dependency is ready because it has bounded retry/recovery, that edge SHALL be documented and acceptance-tested rather than silently left as `service_started`.

### Requirement: Readiness failures are diagnosable

A failed startup SHALL surface which service failed readiness and SHALL retain bounded logs sufficient to diagnose the failure.

## Acceptance evidence

The archived change SHALL contain:

- before/after tables for every dependency edge and health check;
- the exact count of `service_started` edges before and after, with every retained edge justified;
- a live cold-start proof from fresh volumes;
- at least one delayed/unavailable dependency scenario proving the consumer does not falsely become ready or corrupt state;
- a non-vacuous fitness test that fails on a synthetic or captured regression;
- the relevant Compose config validation, unit/integration gates and H1/clean-stack evidence required by the repository contract.

## Rollback

Readiness probes and dependency conditions SHALL be independently revertible without deleting data volumes or changing canonical data. A probe that causes false negatives SHALL be removable while the prior retry/startup behavior is restored.

## Hard stops

Stop if a proposed health check is only cosmetic, if it introduces a correctness dependency on an optional profile, or if changing startup ordering masks rather than tests an application's required recovery behavior.

## Freshness of external assumptions

Reverify current Docker Compose health/dependency semantics at promotion. Repository behavior and pinned service versions SHALL be measured again from current `main`.