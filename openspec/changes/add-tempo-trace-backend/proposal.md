# NG-0.5 — Grafana Tempo trace backend (Milestone 1)

## Scope

This authorised change covers recovery, primary-source revalidation, design,
and preflight for `add-tempo-trace-backend`. It does not implement Tempo,
change the Collector runtime, instrument services, provision a bucket, or
alter the Prometheus/Grafana metrics authority.

The design targets the smallest future `observability-next` profile: existing
applications continue to export only OTLP to the NG-0.4 Collector, and the
Collector's named `telemetry-backend` slot is the only normal write path to a
Tempo monolith. Tempo storage is a dedicated trace namespace, replaceable S3-
compatible object storage, with bounded retention and measured resource use.

## Non-goals and scope fence

- No Tempo container, image pull, datasource, bucket, credentials, or CI job is
  created in Milestone 1.
- No Loki, trace-to-logs runtime, metrics-generator, spanmetrics connector,
  application metric changes, OTLP route change, Kafka/schema/partition change,
  canonical persistence change, or engine-version change.
- Existing Prometheus/PostgreSQL metrics remain authoritative. Grafana remains
  the single UI.
- Trace-to-logs is only a future NG-0.6-compatible mapping contract.

## Preflight outcome

Repository recovery and compatibility review are complete. The former
metric-to-trace contradiction is resolved by archived prerequisite
`2026-09-03-add-prometheus-trace-exemplars` at closure `fe56e19`: an existing
application Histogram now carries bounded sampled-trace exemplar metadata,
without changing metric labels or enabling span-derived metrics. The NG-0.5
design is therefore ready for a separately authorised implementation
milestone; Tempo itself remains unimplemented.
