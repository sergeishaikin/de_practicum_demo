# Prometheus Trace Exemplars — Milestone Receipt

Captured 2026-09-03 from starting SHA
`30e7debe27fe2b9d008393ed61b701ab9e1c4560`.

## Status

Implementation and live prerequisite proof complete; final gates and archive
remain before closure.

## Standing-spec clarification

`openspec/specs/observability-telemetry/spec.md` now explicitly forbids
`trace_id`/`span_id` as time-series labels or dimensions while permitting them
as bounded exemplar metadata on existing application observations. Exemplar
metadata does not increase series cardinality or become business/SLO authority.
The spanmetrics/metrics-generator lockout is unchanged.

## Existing metric selected

`lakehouse_duration_seconds` Histogram, with its unchanged declared label set
`("source",)`. No new metric family was added and no PostgreSQL durable metric
row was changed.

## Trace-context mapping

The helper reads the active OTel span only with `OTEL_ENABLED=1`, valid context
and sampled trace flags. It maps the trace ID to lower-case 32-hex
`{"trace_id": "<id>"}` exemplar metadata. Disabled, unsampled, invalid or
missing SDK contexts return `None`.

## OpenMetrics exemplar proof

Pinned application image `de-practicum-demo-iceberg:0.11.1-h1` (current code
mounted read-only) ran a real `opentelemetry.sdk.trace.TracerProvider` span.
The endpoint returned:

```text
lakehouse_duration_seconds_bucket{le="2.5",source="writer"} 1.0 # {trace_id="5103d7af77a2cb20479d9e4920b54b0f"} 1.25 <timestamp>
```

The same run confirmed `TRACE_ID_LABELS = ('source',)` and an observation
outside an active span contained no exemplar. Focused tests cover both paths
and invalid-exemplar fail-open fallback.

## Prometheus storage proof

Pinned image digest
`prom/prometheus@sha256:63805ebb8d2b3920190daf1cb14a60871b16fd38bed42b857a3182bc621f4996`
reported version `3.5.0` and accepted `--enable-feature=exemplar-storage`.
Startup log reported “Experimental in-memory exemplar storage enabled”. The
config sets `storage.exemplars.max_exemplars: 1000`.

An isolated temporary Docker network scraped the application target
`iceberg-writer:9101`. Prometheus returned `up{job="iceberg-writer"} 1` and
`/api/v1/query_exemplars?query=lakehouse_duration_seconds_bucket` returned the
source trace ID, including the unchanged series labels (`job`, `instance`,
`le`, `source`). Containers and network were removed after the proof.

## Series-cardinality / label proof

The application Histogram's declared label names remain only `source`; no
sample label contains `trace_id`. Prometheus exemplar output places `trace_id`
outside the MetricSet, and the API response reports it under `exemplars`, not
`seriesLabels`.

## Fail-open proof

Unit tests verify disabled/unsampled omission and invalid exemplar metadata
fallback to the same duration observation. No exception crosses into the
metric or canonical processing path. Existing OTel/Prometheus/PostgreSQL
authority remains unchanged.

## Resource bound

`max_exemplars: 1000` is the explicit demo ceiling. Prometheus documentation
estimates approximately 100 bytes for a trace-ID exemplar in memory, or about
100 KiB payload capacity, plus normal WAL/TSDB overhead. This is not a
production sizing claim.

## Primary sources

- [Prometheus exemplars feature flag](https://prometheus.io/docs/prometheus/latest/feature_flags/)
- [Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
- [client_python exemplars](https://prometheus.github.io/client_python/instrumenting/exemplars/)
- [Grafana trace-to-metrics correlation](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-metrics/)

## Gates

Focused tests and changed-surface gates are run before closure. Full repository
pytest/coverage, Compose validation, strict OpenSpec and backlog validation are
the remaining closure checklist items.

## CI

The existing `ci-pr` unit/coverage path automatically includes the focused
exemplar tests; no second framework or core H1 path is introduced. A later
NG‑0.5 capability job owns the final Grafana→Tempo destination proof.

## Archive / standing capability

Not archived yet. Archive only after all gates pass; retain this evidence and
leave NG‑0.5 `ACTIVE/pending`.

## Closure SHA

Pending final commit.

## NG‑0.5 state

`ACTIVE / BLOCKED PENDING RECONCILIATION` until this prerequisite is archived
and referenced by a short NG‑0.5 M1R reconciliation.
