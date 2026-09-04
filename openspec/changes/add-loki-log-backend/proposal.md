# Proposal: add-loki-log-backend

## Milestone 1 boundary

This authorised milestone recovers the merged NG-0.5 baseline, revalidates Loki
and native OTLP assumptions, inventories first-party logging, and records an
implementation-ready design and preflight receipt. It does **not** implement
Loki, change Compose or Collector configuration, instrument production code,
add CI, or alter the Prometheus/Grafana metrics path.

## Problem

The platform has first-party traces but no centrally searchable log backend.
Application output is mostly stdout/plain text, so operators cannot reliably
search by execution identity or navigate between a Tempo span and its logs.
The missing capability must preserve canonical processing, keep labels
low-cardinality, and fail open when observability is unavailable.

## Proposed bounded change

Add an opt-in Loki profile fed by the existing OpenTelemetry Collector through
Loki's native OTLP HTTP endpoint. First-party logs will use a deterministic
schema; only reviewed service/environment labels will be indexed, with trace,
run, load, Kafka and business context retained as structured metadata. Storage
will use a dedicated Loki prefix and finite Compactor-managed retention. Grafana
trace-to-logs will use the existing Tempo datasource plus a provisioned Loki
datasource, without making Loki a dependency of the core stack.

## Scope fence

- No implementation in Milestone 1.
- No Docker daemon/host-log collection, privileged mounts, payload schemas,
  persistence, Spark/Airflow versions, or replacement of Prometheus/Grafana.
- NG-0.6 remains `ACTIVE / pending`; adoption and archive require later
  explicit authorisation and executed evidence.

## Preflight outcome

`PASS_WITH_EXPLICIT_LIMITATIONS`: Loki 3.7.7 native OTLP support and an
amd64 image were verified, and exact baseline H1 run `33869184341` succeeded.
The design is ready for implementation **in a later, explicitly authorised
Milestone 2**. Local resource measurements, final credential wiring,
first-party logging adapters, and persisted redaction/failure evidence remain
implementation and acceptance work.
