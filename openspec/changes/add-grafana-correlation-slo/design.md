# Design: Grafana correlation, operational UI and SLI/SLO layer

## Recovery and product inventory

The M1 branch starts at `d031679de39006f14493fd178ac0b9ff32919498`, whose
consolidation H1 is GitHub Actions run `33908268598` (both jobs successful).
The repository has one provisioned dashboard (`lakehouse-runtime`, UID
`lakehouse-runtime`) with four row sections and seven time-series panels. The
provider is file-backed, `editable: false`, and `disableDeletion: true`.
Prometheus, Tempo and Loki datasources are provisioned with stable UIDs;
Prometheus points exemplars to Tempo, Tempo has `tracesToLogsV2`, and Loki has
a `trace_id` derived field to Tempo. No dashboard variables, panel data links,
annotations or provisioned Grafana alert rules are present. Prometheus has five
repository-managed alert rules.

Panel inventory (all existing panels are retained for M2 assessment):

| Panel | Query/source | Authority and labels | Exemplar/link | SLI/SLO candidate |
|---|---|---|---|---|
| Application events by status | `lakehouse_events_total` rate | application runtime; `source,status`; bounded | no direct exemplar; contextual link only | pipeline success (measured existing) |
| Source availability | `lakehouse_source_up` | PostgreSQL projection; `source` | no | source health (measured existing) |
| Work state | `lakehouse_work` | application runtime; `source,state` | no | backlog health (measured existing) |
| Maintenance health | `lakehouse_maintenance_up` | durable `marts.maintenance_runs` projection; none | no | maintenance health (measured existing) |
| Correctness signals | `lakehouse_correctness_total`, Spark DLQ | application/Spark counters; `source,kind` or none | no direct exemplar | correctness (measured existing) |
| Stage duration | `lakehouse_stage_duration_seconds` | application runtime; `source,stage` | no direct exemplar | boundary duration (measured existing, not end-to-end) |
| Processed/files/bytes | `lakehouse_processed`, `lakehouse_files`, `lakehouse_bytes` | application runtime; `source,kind` | no | throughput/context only |

`marts.lakehouse_metrics` is durable authority. Its cycle envelope is the only
phase row exported to Prometheus; nested phase rows remain PostgreSQL-only.
Consumers must use `iceberg.common.ops.classify_metric_row` and filter cycle
rows where totals are required, rather than re-deriving phase semantics.

## External premise register

| Premise | Result | Evidence |
|---|---|---|
| Grafana file provisioning supports checked-in dashboards/datasources | VERIFIED | Grafana provisioning documentation |
| Prometheus exemplar datasource destination can navigate to Tempo | VERIFIED_WITH_LIMITATIONS | Repository datasource config; Grafana trace docs. Only metrics that emit exemplars can navigate. |
| Tempo `tracesToLogsV2` and Loki derived fields provide both directions | VERIFIED | Grafana trace-to-logs documentation. Both datasources and shared trace ID are required. |
| Low-cardinality labels with trace IDs in structured metadata are supported | VERIFIED | Grafana trace-to-logs/cardinality guidance; adopted NG-0.6 contract. |
| Grafana alerting/data-link provisioning is available | VERIFIED_WITH_LIMITATIONS | Grafana provisioning/data-link docs; exact repository alert-as-code shape is not yet selected. |
| OpenMetadata entity lookup by FQN and stable API `href` | VERIFIED | OpenMetadata API conventions and lineage API. |
| OpenMetadata UI route/FQN deep-link is stable across rebuilds | VERIFIED_WITH_LIMITATIONS | FQNs are stable; entity UUIDs may change and UI route was not independently exercised in M1. |
| Reproducible OpenMetadata-to-Grafana external backlink | UNVERIFIED | Custom properties/entity references exist, but no checked-in external-link mechanism is demonstrated. Treat as limitation, not an implementation assumption. |
| Pinned versions | VERIFIED | Local image probes: Grafana 11.2.0, Prometheus 3.5.0, Tempo 3.0.3, Loki 3.7.7, OTel Collector 0.157.0; OpenMetadata 1.13.3 from adopted evidence and pinned digest. |

## One canonical incident story

M2 should use one controlled medallion operation that records a failed or
unhealthy outcome without changing business data: inject a deterministic shadow
mismatch in an isolated acceptance fixture. The operator starts at the existing
`LakehouseShadowMismatch` alert/panel, whose authoritative expression is
`increase(lakehouse_correctness_total{kind="shadow_mismatches"}[5m]) > 0`.
Because that counter does not emit exemplars, the panel must provide bounded
time/source context and navigate to the same operation's
`lakehouse_duration_seconds` histogram exemplar when one is actually present;
absence of an exemplar is an explicit degraded branch, not a fabricated link.
The selected trace carries `lakehouse.load_id` and `cycle_id` as span/context
attributes (not Prometheus/Loki labels). Tempo-to-Loki uses the adopted
`service_name`/`service_namespace` stream labels and exact trace filter. The
known output dataset is `lakehouse_trino.iceberg.gold.orders_daily_metrics`;
OpenMetadata lineage then shows the proven Bronze/Silver/Gold path and the dbt
semantic downstream context. Any hop not available in the fixture is reported
as a gap rather than inferred.

## Identity and hop contracts

| Hop | Contract |
|---|---|
| Metric → trace | Use the existing Prometheus exemplar destination to Tempo; never add `trace_id` as a label. Duration histogram exemplars are optional and sampled. |
| Trace → logs | Reuse Tempo `tracesToLogsV2` with low-cardinality service labels and exact trace filter. |
| Logs → trace | Reuse Loki structured-metadata `trace_id` derived field to Tempo. |
| Trace/log → execution | Display `run_id`, `load_id`, `cycle_id` as bounded event/span fields or query filters; never index them as labels. |
| Execution → dataset | Use the first-party operation's deterministic mapping: medallion cycle → `gold.orders_daily_metrics`, with cycle/load evidence from PostgreSQL and trace context. |
| Grafana → OpenMetadata | Generate a configured, credential-free link from the canonical FQN to the metadata UI/API route. Validate exact route in M2; FQN, not UUID, is the stable key. |
| OpenMetadata → Grafana | Prefer a checked-in custom property/entity link if the pinned UI/API supports it. Otherwise record `PASS_WITH_LIMITATION`; do not add custom portal code. |

OpenMetadata remains catalog/lineage authority; Grafana remains operational UI.
Grafana shows concise dataset and execution context, not a duplicate lineage
graph.

## SLI dictionary and SLO policy

| SLI | Classification | Source/query and semantics | Missing-data/threshold policy |
|---|---|---|---|
| Pipeline/run success | MEASURED_EXISTING | `lakehouse_events_total{status="success"}` and durable `marts.lakehouse_metrics` status; aggregate by source and bounded window | No data is unknown, not success. Existing alert semantics remain. |
| Boundary latency | MEASURED_EXISTING | `lakehouse_duration_seconds`/`lakehouse_stage_duration_seconds`; operation/stage duration only, not end-to-end unless both timestamps exist | No end-to-end claim. New threshold provisional. |
| Source freshness | MEASURED_EXISTING | Existing source timestamp gauges/warehouse freshness checks | Evaluates only when a source timestamp exists. |
| Missing arrival | REQUIRES_NEW_SIGNAL | No authoritative expected-arrival schedule/signal in baseline | Freshness makes no detection claim; no alert in M1. |
| Streaming lag/checkpoint | MEASURABLE_WITH_EXISTING_DATA | Spark batch/last-batch and checkpoint evidence where present | Scope to existing Spark evidence; do not invent a lag gauge. |
| Metadata/lineage freshness | REQUIRES_NEW_SIGNAL | OpenMetadata ingestion/runtime timestamps are not an authoritative SLI today | Must be separately measured before threshold adoption. |
| Telemetry pipeline health | MEASURED_EXISTING | Collector health/queue metrics and Prometheus scrape health | Observability degradation is explicit and fail-open. |

No production number is adopted in M1. All new thresholds are
`PROVISIONAL/UNMEASURED`; existing alert windows are documented behavior, not
new SLO commitments. Evidence needed for adoption is a bounded historical
window, denominator, owner and missing-data policy.

## Dashboard and alert design (no implementation in M1)

Evolve `lakehouse-runtime`; do not create a second dashboard. Retain its four
sections, add a bounded incident-navigation section, and use only low-cardinality
variables such as `source`, `service_name` and bounded environment. Never offer
`trace_id`, `run_id`, `load_id`, `cycle_id` or dataset FQN as dropdown variables.
Panel queries must constrain time range and stream selectors; exact trace IDs
belong after a bounded stream selector or in structured metadata.

Candidate alerts are design-only. Each must name the authoritative metric,
window, missing-data behavior, failure mode, noise source, correlation target
and threshold status. The existing shadow-mismatch and application-failure
rules are candidates for links; no new alert is production-ready without
measured evidence.

## Security, cardinality and fail-open contracts

Links contain configured host/base URLs and FQNs only; no API keys, cookies,
tokens or credentials. No arbitrary user-controlled URL construction is
allowed. Stable configuration is supplied by provisioning/environment.

Grafana, Prometheus, Tempo, Loki and OpenMetadata outages degrade navigation
only. Canonical Kafka/Spark/Iceberg/PostgreSQL processing and the direct
Prometheus path remain independent. Acceptance must demonstrate metric-only,
trace-without-logs and observability-without-metadata branches.

## Implementation gate and hard stops

Future capability CI must prove provisioning, datasource resolution, same-trace
exemplar/TraceQL/LogQL navigation, execution identity, credential-free
OpenMetadata deep-link, downstream impact where already proven, bounded
variables, visible provisional thresholds, freshness/arrival separation and
fail-open canonical processing. Core H1 remains independent.

Stop and re-plan if this requires a custom portal, product replacement,
application-to-backend coupling, spanmetrics/metrics-generator, high-cardinality
labels, arbitrary SLO numbers, manual dashboard edits, new broad
instrumentation, or NG-0.8 functionality.
