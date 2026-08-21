## Current-state recovery

The recovered baseline is branch `test/dbt-extensive-testing` at commit
`6d9ad95` (2026-08-20). The worktree was clean. `uv run --locked python
openspec/backlog/validate_backlog.py` passed before promotion, and is expected
to pass again after the active change directory is present.

The existing observability authority is unchanged:

- `iceberg/common/ops.py` records durable PostgreSQL metrics and exposes the
  application Prometheus endpoint;
- Spark exposes a Prometheus endpoint;
- `observability/postgres_exporter.py` projects durable metrics;
- `observability/prometheus/prometheus.yml` scrapes writer, medallion,
  streaming and exporter targets;
- Grafana is provisioned from `observability/grafana`.

The core Compose graph has no Collector, Tempo or Loki service. The only
Collector-related material currently present is transitive Airflow/OpenLineage
dependency resolution in `airflow.requirements.txt`; the root environment and
the checked-in service virtual environment do not provide an installed OTel
SDK. This is an implementation input, not a reason to mutate the baseline in
Milestone 1.

## Decisions

### Boundary and deployment

Applications export new traces and logs to one OTLP/gRPC endpoint owned by the
Collector. The implementation contract is `OTEL_EXPORTER_OTLP_PROTOCOL=grpc`
and `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`, with a 5-second
export timeout. The receiver binds `0.0.0.0:4317` on the Compose network only;
no OTLP host port is published. OTLP/HTTP (`4318`) is not enabled in this
change. TLS is not used on the isolated local Compose network; a deployment
outside that network must not silently reuse this profile.

The selected distribution is the official **OpenTelemetry Collector Contrib**
(`otelcol-contrib`), using the canonical GHCR image
`ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.157.0`.
The implementation MUST replace the tag with the exact immutable image digest
and record the digest in the change evidence before it is merged. Core,
Kubernetes, custom-builder and vendor distributions are out of scope.

The component allow-list is intentionally small: `otlp` receiver (gRPC),
`memory_limiter`, `batch`, `filter`/`attributes` redaction processors,
`debug` exporter for the NG-0.4 smoke path, `file_storage` extension for the
selected WAL queues, and `health_check` extension. Components outside this
set require a separately recorded design decision. In particular, no Kafka
exporter, vendor exporter, `spanmetrics` connector or automatic host/process
receiver is admitted by NG-0.4.

Existing Prometheus endpoints remain directly scraped. Collector self-metrics
are exposed on a Prometheus-compatible endpoint and added to the existing
scrape path without removing any target.

The Collector is an opt-in Compose profile with a persistent, least-privilege
storage volume. Core processing must remain startable with that profile
disabled. Backend routing is deliberately deferred to NG-0.5/NG-0.6; the
Milestone 2 profile uses only the `debug` exporter as its backend-neutral smoke
sink until those items are separately authorised. The implementation MUST
insert a future backend exporter in the Collector configuration only: NG-0.5
or NG-0.6 may add a named exporter under the `telemetry-backend` slot and wire
that slot into the traces/logs pipelines. Applications and their OTLP endpoint
MUST NOT change when a backend is added; no per-service Tempo/Loki/vendor
configuration is permitted.

### M1B backend and metrics authority freeze

The OTLP receiver and application exporter contract above is frozen for M2.
Backend insertion is a Collector config/profile change behind the named
`telemetry-backend` slot, with one backend exporter per signal and no direct
application-to-backend path. The `debug` exporter is the only M2 default and
is not a durable backend.

Operational metric authority remains unchanged. `iceberg/common/ops.py` and
the durable PostgreSQL metrics path remain authoritative for business/pipeline
metrics; existing Prometheus endpoints remain authoritative for live
application metrics. Collector self-metrics are authoritative only for
Collector health, queue, retry and drop diagnostics. NG-0.4 SHALL NOT add a
`spanmetrics` connector, convert spans into SLO/business metrics, or migrate a
Prometheus metric to OTLP. Any future span-derived metric or metric migration
requires explicit equivalence evidence and a separately authorised OpenSpec
change. This is a lockout, not a deferred implementation task.

### Resource identity and correlation

Every first-party resource sets deterministic `service.name` and a stable
`service.namespace`; deployment environment uses the currently documented
`deployment.environment.name` resource attribute. Container IDs, process IDs
and hostnames are never service identity. NG-0.1 canonical identifiers map to
OTel attributes as documented vocabulary, while trace/run/cycle/load IDs remain
attributes or links and never Prometheus labels.

### Python instrumentation scope

Milestone 2 starts with the Iceberg writer, medallion and custom observability
exporter only where they perform work. Instrumentation is explicit and narrow:
span around a batch/cycle and its externally visible calls, structured logs
with correlation context, and bounded attributes. Airflow, Spark and Flink
use supported integrations or bounded adapters; no monkey-patching.

### Kafka context contract

The producer and consumer use the actual `confluent-kafka==2.15.0` libraries.
Propagation tests must inject/extract W3C trace context through Kafka headers
and verify header encoding, missing/invalid headers and multi-header behaviour.
Consumer processing creates a new process span with a link to the producer
context when asynchronous parentage is not semantically valid. Topic,
partition, consumer group and offset are bounded attributes; payloads and
keys are not recorded by default. Messaging semantic-convention mode and the
OTel dependency versions are pinned in the implementation change.

### Queue, retry and WAL contract

Every network exporter has an explicit bounded sending queue and retry policy:
queue capacity in batches, batch size, retry initial/max interval, maximum
elapsed retry horizon, and a disk budget. The Collector uses the `file_storage`
extension only for signal classes whose restart-loss budget requires it. WAL is
not infinite retention: disk-full, queue-full and retry-timeout are expected
drop modes and must be counted and alerted. The implementation must test a
Collector restart, backend outage, queue overflow and recovery drain.

### Redaction, sampling and failure behaviour

Application instrumentation denies secrets, auth headers, connection strings,
full SQL literals, full Kafka payloads and arbitrary PII by default. A
Collector filter/redaction processor is a second boundary, not the sole
defence. Sampling is initially `always_on` only for the bounded demo workload;
any later head/tail policy must preserve errors and critical paths and declare
its policy in configuration.

Exporter or Collector failure is fail-open for canonical processing: bounded
timeouts and queues may lose telemetry after declared limits, but may not alter
Kafka offsets, Iceberg writes, PostgreSQL warehouse state or business results.
Loss, refusal, receiver errors and queue pressure remain visible through
Collector/application metrics and logs.

## Compatibility and resource preflight

Primary-source revalidation confirms that the current OpenTelemetry Python
exporter documentation supports OTLP/gRPC and OTLP/HTTP to a Collector, and
that the Collector resiliency documentation defines bounded sending queues,
retry horizons and `file_storage` WAL with explicit queue-full, timeout and
disk-failure loss modes. The current Kafka semantic-convention document is
still marked Development and documents `OTEL_SEMCONV_STABILITY_OPT_IN`; this
supports pinning the convention mode rather than assuming stability.

Read-only host probes found Docker Engine 29.5.3 with a 15.49 GB Docker memory
allocation (8 CPUs), and the existing Compose configuration passed with the
committed `.env.example` pins. No Collector image is cached, so image size and
runtime overhead remain implementation measurements. The baseline local
profile is approximately 0.7 GB while idle; Milestone 2 must measure the
Collector profile against that floor and record CPU, RSS, queue disk use and
telemetry throughput.

## Milestone 2 implementation status

The opt-in profile and first-party Python export path are implemented within
the frozen boundary. Writer, medallion and durable-metrics exporter telemetry
is disabled by default and fail-open when enabled. The producer now injects
W3C `traceparent` into Kafka headers without changing payload bytes, keys,
partitions or offsets. No consumer schema or Spark/Airflow version changed.

The Collector uses the pinned Contrib digest, OTLP/gRPC receiver, bounded
memory/batch processors, redaction processor, `file_storage` extension and
debug sink. The debug sink is deliberately backend-neutral; no Tempo/Loki or
other NG item is included. Existing Prometheus targets and PostgreSQL durable
metrics remain untouched; only Collector self-metrics are added as an opt-in
scrape target.

The live standalone Collector smoke reached `Everything is ready` and the
image config validator passed. A full backend-outage/queue-drain test is not
claimable in NG-0.4 because no telemetry backend is authorised or configured;
the remaining M2 evidence records this limitation rather than inventing a
loss/recovery result.
