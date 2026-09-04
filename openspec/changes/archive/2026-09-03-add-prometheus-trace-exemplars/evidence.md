# Prometheus Trace Exemplars — Milestone Receipt

Captured 2026-09-03 from starting SHA
`30e7debe27fe2b9d008393ed61b701ab9e1c4560`.

## Status

Implementation, live prerequisite proof, exact-SHA CI and final gates complete;
the prerequisite is archived and adopted.

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
fallback to the same duration observation. Exemplar shape is validated before
Histogram mutation; the implementation does not retry after an `observe()`
exception, avoiding double-counting in client versions that may mutate before
validating metadata. The reserved `__invalid` regression asserts count `1`
and sum `1.25`. No exception crosses into the metric or canonical processing
path. Existing OTel/Prometheus/PostgreSQL authority remains unchanged.

## Verification-contract repair

The regression was first run against the unfixed implementation at detached
SHA `fe56e19172e6535987e2c9c59a92dfd85270dc5d`, using the repaired
`__invalid` test. It failed as expected with
`lakehouse_duration_seconds_count == 2.0` (the old fallback retried after
client-side mutation). The temporary proof worktree was then removed.

The same test passes on repaired SHA `229882b85eadfcddc5ae31b535b36f9748ac7cc9`
with count `1` and sum `1.25`.

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

- `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing
  --cov-fail-under=90`: 517 passed, 1 skipped, 81 deselected; 93.31% coverage.
- `uv run --locked pytest`: 517 passed, 1 skipped, 81 deselected.
- `uv run --locked ruff check .`: passed.
- `uv run --locked black --check .`: passed.
- `uv run --locked mypy`: passed (10 source files).
- `openspec validate add-prometheus-trace-exemplars --strict`: valid.
- `openspec validate --specs --strict`: 5 passed, 0 failed.
- Compose config and pinned-image `promtool check config`: passed.
- `git diff --check`: passed.

## Exact-SHA CI receipt

Head SHA `229882b85eadfcddc5ae31b535b36f9748ac7cc9` was exercised by PR [#3](https://github.com/sergeishaikin/de_practicum_demo/pull/3)
and all required jobs passed:

- [CI](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33745729020): lint/compose, unit+coverage, dbt artifacts and Airflow validation.
- [M5 architecture gates](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33745729022): recovery and cutover gates.
- [Metadata profile](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33745729019): isolated metadata acceptance.
- [H1 clean reproducible stack](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33745729092): fresh-volume full verification and NG‑0.4 OTel acceptance.

The PR was fast-forward merged at the exact prerequisite SHA. No Tempo
implementation or span-derived metric path was introduced.

## Archive / standing capability

Archived as `2026-09-03-add-prometheus-trace-exemplars`; retain this evidence
and leave NG‑0.5 `ACTIVE/pending`.

## Repair receipt

Post-review repair was applied after the original archive commit: invalid
exemplars are rejected before observation, and writer metric spans carry the
bounded `lakehouse.load_id` trace attribute. Focused tests, full coverage and
typing/lint gates were rerun successfully.

## Closure SHA

Repair closure commit: `229882b85eadfcddc5ae31b535b36f9748ac7cc9`.
This receipt update is documentation-only; implementation content and the
exact-SHA CI target remain unchanged.

## NG‑0.5 state

`ACTIVE / pending` with M1R reconciliation recorded on the rebased NG‑0.5
branch. NG‑0.5 implementation remains separately unauthorised.
