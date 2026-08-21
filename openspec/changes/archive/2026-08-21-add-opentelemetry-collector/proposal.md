## Authorisation and milestone fence

NG-0.4 was explicitly authorised by the operator on 2026-08-20 under
`operator:explicit-ng-0.4-milestone-1`. This change is currently limited to
Milestone 1 and the explicitly authorised Milestone 2 implementation. Milestone
1B freezes the backend contract below; implementation remains limited to NG-0.4
and does not adopt NG-0.5/0.6/0.7 backends.

The later M3A acceptance and M3B final adoption/CI/archive continuations were
also explicitly authorised by dated operator instructions. No separate
authorisation identifiers were supplied; the original grant identifier above
remains the lifecycle provenance and the continuation receipts are recorded in
`evidence.md`.

The implementation does not alter Kafka records/partitioning, canonical
persistence, Prometheus/Grafana ownership, or Spark/Airflow versions.

## Why

The backlog defines a vendor-neutral OTLP boundary, bounded Collector
resilience, context propagation, redaction and sampling rules, but explicitly
marks versions and capability claims as stale while unauthorised. The design
must therefore be revalidated against the repository and current primary
OpenTelemetry documentation before implementation can be accepted.

## What this milestone delivers

- A recovered repository baseline and lifecycle promotion to `ACTIVE`.
- A design contract for the Collector, first-party Python instrumentation,
  OTLP transport, Kafka propagation, queue/retry/WAL, redaction, sampling,
  resource limits, failure injection and CI gates.
- A required `observability-telemetry` specification delta.
- Evidence for read-only compatibility/resource probes and a clear
  implementation readiness classification.
- A frozen distribution, OTLP/network, backend insertion and span-metrics
  authority contract for a later implementation grant.

## Non-goals

- No production code, dependencies, Compose services, images, dashboards or
  CI workflow changes.
- No backend adoption (Tempo/Loki), Grafana correlation work or other NG item.
- No claim of lossless telemetry or automatic third-party instrumentation.

## Scope fence

Only `openspec/backlog/next-generation/00-INDEX.md`, the NG-0.4 lifecycle
header, and files under `openspec/changes/add-opentelemetry-collector/` may be
changed by Milestone 1. Milestone 2 implementation requires a new explicit
operator approval after this report.
