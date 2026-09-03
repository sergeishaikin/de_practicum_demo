# Design and preflight contract

## Baseline and ownership

Baseline is adopted NG-0.4 closure `c151470c51a142ce8142166505b39ada861d094e`
on branch `feature/ng-0.5-tempo`. NG-0.4 is `DONE/ADOPTED`; NG-0.5 is
`ACTIVE/pending`; NG-0.6 remains `PLANNED` and is not authorised. The only
authorised work in this change is M1 design/preflight.

NG-0.5 owns the future Tempo image/config/profile, dedicated trace storage,
retention/compaction settings, Grafana Tempo datasource, TraceQL/query smoke,
and profile evidence. Shared Collector routing, Grafana provisioning
registration and lifecycle metadata are touched only minimally and only after
a later implementation grant.

## Proposed topology (not implemented)

`application → OTLP/gRPC Collector:4317 → telemetry-backend → Tempo monolith →
dedicated S3-compatible trace bucket → Grafana Tempo datasource`.

The applications never name Tempo. A monolith (`-target=all`) is the smallest
demo topology and avoids introducing Kafka into the trace backend. A later
production deployment may use Tempo microservices and a Kafka-compatible queue,
but that is outside this change. The current Collector remains opt-in and
fail-open; its bounded queue/retry/WAL contract and redaction are reused.

## Storage, retention and recovery contract

The implementation must use a dedicated trace bucket/prefix (for example,
`tempo-traces`) and a dedicated credential with no Iceberg warehouse access.
The local MinIO endpoint is a demo convenience only; endpoint, bucket, prefix,
credentials and TLS are externalised so S3/GCS/Azure or another S3-compatible
store can replace it. Cleanup ownership and match scope must be explicit and
must never match `de-practicum/warehouse` or other canonical prefixes.

Retention must be finite, with compaction and block-retention values recorded
together. Restart/recovery must prove that Collector WAL/queue semantics remain
bounded and that canonical processing is unaffected by Tempo outage or storage
failure. A representative workload must measure trace-object growth, peak RAM,
CPU and disk; no synthetic capacity claim is accepted as production sizing.

## Identity, query and security contract

Search and smoke tests use stable `service.name`, `service.namespace`,
`deployment.environment` and bounded execution context, plus a known trace ID.
Ephemeral container names and unbounded business identifiers are not the sole
search keys. Existing NG-0.4 redaction remains authoritative: no secrets,
auth headers, connection strings, full SQL literals, payloads or PII. Errors
retain status/events sufficient to identify the failing step.

TraceQL examples will be small and repository vocabulary will be selected from
the adopted resource identity during implementation; no new attribute naming
is invented in M1.

## Correlation gate and contradiction

Grafana documentation supports trace-to-metrics links against existing
Prometheus-compatible metrics without requiring Tempo metrics-generator, while
reverse metric-to-trace navigation requires Prometheus exemplars. The current
repository was inspected read-only: `observability/prometheus/prometheus.yml`
contains scrape jobs only; Grafana provisions only the Prometheus datasource;
code/tests contain no exemplar API, OpenMetrics exemplar, `trace_id` metric
sample, or exemplar configuration.

The adopted NG-0.4 standing spec prohibits `spanmetrics` and promotion of
span-derived metrics to business/SLO authority. Consequently the NG-0.5
acceptance scenario “Prometheus panel containing a configured exemplar” is not
currently satisfiable. This is `FAIL_SPEC_CONTRADICTION`, not a missing
container capability. The smallest resolution must be separately authorised:

1. amend/reconcile the NG-0.5 gate to accept one-way trace→metrics only and
   explicitly defer metrics→trace; or
2. authorise a bounded application-metric exemplar contract that preserves
   existing metric authority and does not derive metrics from spans.

Tempo metrics-generator, Collector spanmetrics, or any silent metric-schema
change are prohibited as “fixes”. No implementation starts until the operator
chooses and governs one resolution.

Trace-to-logs is prepared only as a future mapping (`tracesToLogsV2`) to the
stable fields NG-0.6 will define; no Loki datasource or bidirectional proof is
part of NG-0.5.

## Failure, resources and CI

The future profile must test healthy ingestion, Tempo unavailable, restored
backend, Tempo restart, object-store write failure, queue saturation and
Collector WAL recovery. Every case must show canonical writer/medallion/
streaming results unchanged and bounded telemetry loss/pressure visible in
Collector metrics. The profile remains opt-in and core H1 runs with it absent.

CI design is limited to a future capability job: pinned image/digest and
component validation, clean profile start, OTLP/query smoke, isolated-prefix
assertion, retention/disk receipt, and failure injection. It must not alter the
existing core H1 job.
