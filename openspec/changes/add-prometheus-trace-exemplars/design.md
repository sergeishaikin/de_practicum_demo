# Design

## Boundary and ownership

Starting SHA is `30e7debe27fe2b9d008393ed61b701ab9e1c4560`, the NG‑0.5 M1
checkpoint. This change owns exemplar generation in the existing Iceberg
application metrics path, Prometheus exemplar storage/configuration and the
standing-contract clarification. NG‑0.5 owns the eventual Tempo datasource and
metric→trace destination. NG‑0.6 owns Loki.

## Metric and trace mapping

The existing `lakehouse_duration_seconds` Histogram is the representative
operation metric. Its declared labels remain exactly `source`; `trace_id` is
passed only via the Python client's exemplar argument. No other metric is
annotated. The application obtains context from the active OTel span through
`opentelemetry.trace.get_current_span()` only when `OTEL_ENABLED=1`, the
context is valid and sampled. The trace ID is rendered as lower-case, padded
32-character hexadecimal. Unsampled/invalid/no-SDK contexts return no
exemplar, preserving the exact existing observation.

Writer success/error metric calls run inside a short child span so the metric
observation has an actual active trace context; medallion calls already occur
inside `medallion.cycle`. This does not change metric values, labels, payloads,
durable PostgreSQL rows or canonical processing.

If the client rejects exemplar metadata, the code logs the bounded failure and
retries the same observation without an exemplar. The fallback is deliberately
local to the metric call.

## Prometheus storage and exposition

The pinned Prometheus image is started with
`--enable-feature=exemplar-storage`; `observability/prometheus/prometheus.yml`
sets `storage.exemplars.max_exemplars: 1000`. Prometheus documents exemplar
storage as a fixed-size circular in-memory buffer and estimates roughly 100
bytes for a trace-id exemplar, so the configured ceiling is approximately
100 KiB of exemplar payload before normal TSDB/WAL overhead. This is a
demo-appropriate bound, not production sizing.

The global scrape protocol is explicitly `[OpenMetricsText1.0.0]`, because
`prometheus-client` renders exemplars only in OpenMetrics. This prevents a
plain-text negotiation path from silently discarding the correlation metadata.

## Correlation and cardinality contract

The standing contract now distinguishes forbidden time-series labels/dimensions
from permitted bounded exemplar metadata. Exemplar labels do not create new
series and cannot be used for business/SLO aggregation. No span-derived metric
component is introduced. Grafana's future `exemplarTraceIdDestinations`
registration remains NG‑0.5-owned and is not pointed at a nonexistent Tempo
datasource here.

## Failure and security model

OTel SDK absence, disabled OTel, invalid/unsampled context and exemplar
validation errors all fail open to the existing metric update. No trace ID is
written to PostgreSQL durable rows. Existing NG‑0.4 redaction and payload /
secret restrictions remain unchanged. Prometheus outage affects observability
only and cannot alter canonical processing.

## Verification plan

1. Unit/focused tests prove sampled ID formatting, unsampled omission, OpenMetrics
   rendering, unchanged labels, and invalid-exemplar fallback.
2. The pinned Iceberg image runs a real OTel SDK span and exposes the exemplar;
   the same image proves no exemplar outside an active trace.
3. A temporary isolated Docker network runs that application with pinned
   Prometheus. Prometheus readiness, target health, exemplar storage log and
   `/api/v1/query_exemplars?query=lakehouse_duration_seconds_bucket` prove
   ingestion and source trace ID. Containers/network are removed afterwards.
4. Existing full unit, coverage, lint, typing, Compose and OpenSpec gates run;
   no H1 destructive reset is used.
