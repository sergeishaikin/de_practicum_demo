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

## Correlation gate and resolved prerequisite

Grafana documentation supports trace-to-metrics links against existing
Prometheus-compatible metrics without requiring Tempo metrics-generator, while
reverse metric-to-trace navigation requires Prometheus exemplars. Archived
prerequisite `2026-09-03-add-prometheus-trace-exemplars` supplies that primitive:
`lakehouse_duration_seconds` retains its existing `source` label set and carries
only bounded sampled OTel `trace_id` exemplar metadata. Prometheus exemplar
storage is explicitly bounded and OpenMetrics negotiation is configured.

The adopted NG-0.4 standing spec still prohibits `spanmetrics` and promotion
of span-derived metrics to business/SLO authority. The prerequisite changed
neither rule nor metric authority; its evidence proves the former contradiction
is gone. Tempo metrics-generator, Collector spanmetrics, and silent metric
schema changes remain prohibited. NG-0.5 M2 may now implement Tempo only after
a separate implementation grant.

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
