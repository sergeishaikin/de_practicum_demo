# NG-0.4 — OpenTelemetry Collector and Instrumentation Contract

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Product decision

Add **OpenTelemetry Collector** as the vendor-neutral telemetry ingestion/processing layer. Preserve the existing Prometheus/Grafana metrics path during the first adoption wave; OTel extends it with traces/logs and standardized context.

## Dependencies

NG-0.1. NG-0.2/0.3 may proceed in parallel once 0.1 is stable.

## Goal

Provide one OTLP boundary for first-party telemetry so services are not hardwired to Tempo/Loki or another backend, while keeping business processing independent of telemetry availability.

## Non-goals

- No removal of existing Prometheus exporters.
- No claim that every third-party container is automatically instrumented.
- No unbounded trace/log retention.
- No trace IDs as Prometheus labels.
- No "lossless telemetry" claim without testing queue/WAL bounds.

## ADDED Requirements

### Requirement: OTLP is the application export boundary

New first-party trace/log instrumentation SHALL export via OTLP to the Collector rather than directly to Tempo/Loki.

Existing Prometheus metric endpoints MAY remain scraped directly. Migration of a metric to OTLP requires explicit benefit and equivalence evidence.

### Requirement: Stable resource identity

Every first-party OTel resource SHALL set deterministic `service.name`; related services SHALL use a stable `service.namespace`; environment SHALL use the current stable deployment-environment attribute convention.

Ephemeral container IDs SHALL NOT be used as `service.name`.

### Requirement: Context propagation is tested, not assumed

Trace context SHOULD propagate across synchronous service boundaries and Kafka message boundaries where supported. Kafka header propagation SHALL be tested against the actual producer/consumer libraries.

If parent-child continuity is semantically wrong or technically unavailable across asynchronous processing, span links/correlation fields SHALL be used rather than manufacturing a false parent.

### Requirement: Messaging semantic conventions are pinned

Because Kafka/messaging semantic conventions may be non-stable, the emitted convention mode and dependency versions SHALL be pinned. Upgrades that change semantic fields require a compatibility test and dashboard/query update in the same change.

### Requirement: Collector outage does not fail data processing

First-party exporters SHALL be configured so an unavailable Collector does not make canonical data processing fail solely because telemetry cannot be delivered.

Loss/backpressure SHALL be observable through Collector/application metrics.

### Requirement: Bounded resilient export

Network exporters SHALL use bounded sending queues and retry. The Collector SHALL use persistent queue/WAL storage for telemetry classes where loss during Collector restart is considered unacceptable within the demo's bounded recovery window.

The configured queue capacity, retry horizon and disk budget SHALL be explicit and tested. "Persistent" SHALL NOT be equated with infinite retention.

### Requirement: Backpressure and drop metrics are monitored

Collector queue size/capacity, exporter failures, refused/dropped telemetry and receiver errors SHALL be exposed to Prometheus and included in an operational dashboard.

### Requirement: Sensitive data is denied by default

Instrumentation SHALL NOT record secrets, auth headers, connection strings, full SQL containing sensitive literals, full event payloads or arbitrary PII by default.

A Collector processor/filter/redaction policy SHALL supplement application discipline; it SHALL NOT be the only protection.

### Requirement: Sampling policy is explicit

The local demo MAY initially retain all traces at bounded workload. Any sampling introduced later SHALL declare whether it is head/tail sampling and SHALL preserve error/critical-path diagnostic requirements.

### Requirement: Logs/traces/metrics use one correlation vocabulary

OTel attributes SHALL map to NG-0.1 identities without duplicating incompatible names. High-cardinality execution IDs MAY be trace/log attributes but SHALL NOT become unbounded metric dimensions.

## Instrumentation scope

First adoption SHALL instrument first-party Python services at minimum:

- Iceberg writer;
- medallion;
- custom observability exporter where it performs work;
- future API/agent services.

Airflow/Spark/Flink instrumentation SHALL be added only through supported integrations or explicit bounded adapters, not unsupported monkey-patching.

## Non-functional requirements

- **Availability:** telemetry outage does not corrupt/fail canonical processing.
- **Durability:** bounded outage recovery demonstrated for configured WAL/queue.
- **Performance:** CPU/memory/runtime overhead measured for representative workloads.
- **Security:** scrubbed payload policy and least privilege.
- **Compatibility:** pinned semantic convention behavior.
- **Maintainability:** central Collector config, minimal backend-specific application code.

## Failure-injection tests

1. stop a telemetry backend while Collector receives telemetry;
2. prove queues/retries behave within configured bounds;
3. restart backend and prove bounded queued data drains;
4. restart Collector and verify persistent queue behavior where enabled;
5. exceed queue capacity in a controlled test and prove drops are observable rather than hidden;
6. prove data-processing correctness remains unchanged.

## Acceptance gates

- Collector health/readiness;
- OTLP trace + log smoke from one first-party service;
- Collector self-metrics scraped by existing Prometheus;
- negative secret/redaction test;
- no new high-cardinality Prometheus series pattern;
- profile clean-start CI;
- existing Prometheus/Grafana checks green.

## External constraint

OpenTelemetry Collector documentation explicitly describes queue-full/retry-timeout loss modes and persistent `file_storage`/WAL options. This spec therefore requires tested bounded resilience, not an unsupported "Collector is lossless" assumption.

## Rollback

Disable OTel exporters/Collector profile. Existing Prometheus metrics and canonical processing remain operational.

## Hard stops

Stop if instrumentation requires changing business payload schemas, Kafka partitioning, canonical persistence, or third-party engine versions solely to propagate traces.
