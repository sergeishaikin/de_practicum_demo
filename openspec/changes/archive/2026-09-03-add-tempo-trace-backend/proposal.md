# NG-0.5 — Grafana Tempo trace backend (Milestones 1-2)

## Scope

This authorised change covers recovery, primary-source revalidation, design,
preflight, and the bounded Milestone 2 capability implementation for
`add-tempo-trace-backend`. It adds only an opt-in Tempo profile and routes
existing OTLP through the Collector; Prometheus/Grafana metrics remain
authoritative.

The design targets the smallest opt-in `observability-next` profile: existing
applications continue to export only OTLP to the NG-0.4 Collector, and the
Collector's named `telemetry-backend` slot is the only normal write path to a
Tempo monolith. Tempo storage is a dedicated trace namespace, replaceable S3-
compatible object storage, with bounded retention and measured resource use.

## Non-goals and scope fence

- The Tempo profile is optional and isolated; core H1 startup does not require
  it. Final archive/adoption remains outside this milestone.
- No Loki, trace-to-logs runtime, metrics-generator, spanmetrics connector,
  application metric changes, OTLP route change, Kafka/schema/partition change,
  canonical persistence change, or engine-version change.
- Existing Prometheus/PostgreSQL metrics remain authoritative. Grafana remains
  the single UI.
- Trace-to-logs is only a future NG-0.6-compatible mapping contract.

## Preflight outcome

Repository recovery and compatibility review are complete. The former
metric-to-trace contradiction is resolved by archived prerequisite
`2026-09-03-add-prometheus-trace-exemplars` at adopted archive receipt
`5644c49` (implementation repair `229882b`): an existing
application Histogram now carries bounded sampled-trace exemplar metadata,
without changing metric labels or enabling span-derived metrics. The NG-0.5
design was therefore ready for implementation. Milestone 2 now supplies the
bounded implementation and local acceptance receipts in `evidence.md` while
leaving NG-0.5 `ACTIVE/pending` pending explicit final adoption.
