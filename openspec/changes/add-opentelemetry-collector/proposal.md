## Authorisation and milestone fence

NG-0.4 was explicitly authorised by the operator on 2026-08-20 under
`operator:explicit-ng-0.4-milestone-1`. This change is currently limited to
Milestone 1: repository recovery, design, compatibility/resource preflight and
acceptance planning. Milestone 1B freezes the backend contract below; it does
not provision or run the selected distribution.

Implementation is not authorised in this milestone. In particular, this change
does not add a Collector service or image, install SDK dependencies, instrument
Python services, alter Kafka records/partitioning, alter canonical persistence,
replace Prometheus/Grafana, or change Spark/Airflow versions.

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
