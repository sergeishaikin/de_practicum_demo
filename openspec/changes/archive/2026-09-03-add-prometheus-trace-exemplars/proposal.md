# Bounded Prometheus → trace exemplars

## Purpose

Provide the missing correlation primitive required by NG‑0.5: annotate one
existing application metric observation with the current sampled OpenTelemetry
`trace_id`, and make Prometheus retain that exemplar in a bounded in-memory
buffer. This is not a new metric platform and does not derive metrics from
spans.

## Scope

- Reuse `lakehouse_duration_seconds` and its existing `source` label set.
- Read only a valid sampled OTel current span context; use the canonical
  lower-case 32-hex trace ID as exemplar metadata.
- Keep exemplar lookup and metric update fail-open.
- Enable and bound Prometheus exemplar storage; explicitly negotiate
  OpenMetrics for the scrape path.
- Clarify the standing observability contract and add regression/focused tests.

## Non-goals and fence

- No Tempo, Loki, Grafana Tempo datasource, metrics-generator, spanmetrics,
  RED metrics, new metric family, PostgreSQL schema/row, Kafka/data change, or
  canonical processing change.
- `trace_id` is never a time-series label/dimension and never business/SLO
  grouping authority.
- NG‑0.5 remains `ACTIVE/pending`; this change proves only
  application metric → Prometheus exemplar, not Prometheus → Tempo navigation.

## Acceptance outcome

The pinned application image emitted an OpenMetrics exemplar from an actual
sampled OTel span, preserved the existing metric labels, and emitted no
exemplar outside a trace. Pinned Prometheus `3.5.0` accepted the config,
reported exemplar storage enabled, scraped the application target, and returned
the exemplar through `/api/v1/query_exemplars`.
