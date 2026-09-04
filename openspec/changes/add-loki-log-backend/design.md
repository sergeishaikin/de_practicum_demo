# Design: add-loki-log-backend

## 1. Recovery and decision boundary

The authoritative integration baseline is `07b475fd28a831794d817580c1dee09c56d098b9`
on `test/dbt-extensive-testing`; this worktree is `feature/ng-0.6-loki`.
NG-0.5 is already integrated and adopted. This document is design only: no
runtime file, Compose profile, datasource, exporter, or CI workflow is changed
by Milestone 1.

## 2. Version and ingestion choice

The primary Grafana release page lists Loki **3.7.7** (2026-08-27, revision
`7a40404`) as current. A bounded local manifest probe resolved
`grafana/loki:3.7.7` to multi-architecture manifest
`sha256:d70e4659623f3e109af669cae76fe2a5dd5be54e2298fe8aed380d982fbc2500`.
The implementation should pin that immutable manifest digest (and record the
platform digest in evidence when selected), not a mutable tag.

Loki's native OTLP HTTP ingestion is supported. The Collector will use an
`otlphttp` exporter with endpoint `http://loki:3100/otlp`; applications will
continue to emit OTLP to the existing Collector only. The legacy direct Loki
exporter is explicitly out of scope. If authentication is enabled, use the
Collector `basicauth` extension and a secret reference; never place credentials
in logs or command output. Loki must have
`limits_config.allow_structured_metadata: true` (default since 3.0, but set
explicitly) and a schema version supporting structured metadata.

## 3. Storage, schema and retention contract

Use Loki TSDB with schema version 13 and a 24-hour index period. The local
profile may use the existing object-store service, but only through a dedicated
Loki bucket/prefix and least-privilege credentials; a filesystem store is an
acceptable isolated fallback for a disposable probe. TSDB plus Compactor is
the supported new-install path; Table Manager is not to be introduced.

Proposed bounded demo policy (to be confirmed by implementation evidence):

- retention: 48 hours;
- Compactor singleton, compaction interval 10 minutes;
- retention delete delay 2 hours;
- object-store lifecycle, if configured, strictly longer than retention plus
  delete delay and scoped to the Loki prefix.

The Compactor owns cleanup. No retention or lifecycle operation may touch
Iceberg or Tempo prefixes. The implementation must prove a denied write to the
canonical Iceberg/Tempo locations and a successful write only inside Loki's
dedicated location, without printing credentials.

## 4. First-party logging inventory and scope

The baseline inventory found these repository-owned emitters:

| Surface | Evidence | M1 classification | M2 disposition |
|---|---|---|---|
| Iceberg writer | `iceberg/writer/iceberg_writer.py` (`print`, errors) | PLAIN_TEXT | adapter to schema; preserve stdout |
| Iceberg medallion | `iceberg/medallion/iceberg_medallion.py` (`print`, errors) | PLAIN_TEXT | adapter; include cycle/load/snapshot context as metadata |
| Kafka producer | `kafka/producer/orders_producer.py` (`print`, delivery errors) | PLAIN_TEXT | OUT_OF_SCOPE for first adopted wave: producer image does not carry the OTel SDK; delivery callback remains stdout/Prometheus evidence |
| Spark streaming jobs | `spark/jobs/orders_streaming.py` (`print`) | PLAIN_TEXT | OUT_OF_SCOPE for first adopted wave: Spark driver/executor lifecycle is framework-owned and adding SDK packaging would change the Spark image contract |
| Airflow DAG code | `dags/lakehouse_maintenance.py` (`print`, traceback) | PLAIN_TEXT | OUT_OF_SCOPE for first adopted wave: scheduler/provider logs are excluded and task image has no approved OTel boundary |
| Prometheus/telemetry service | `observability/telemetry.py` | STRUCTURED_PARTIAL | retain metrics path; add log records through existing Telemetry boundary |
| Shared OTel helper | `iceberg/common/telemetry.py` | OTEL_LOG_READY | reuse OTLP logger, add schema/redaction policy |
| one-shot verification/migration scripts | `scripts/`, verification jobs | OUT_OF_SCOPE by default | collect only explicitly named acceptance events |

Kafka delivery callbacks, Spark jobs and Airflow task code are therefore out of
scope for the first adopted wave for the concrete
packaging/lifecycle reasons above. Third-party Kafka, Spark, Airflow, Grafana,
Tempo, MinIO, Trino and container daemon logs are not claimed either. Their
exclusion is a documented coverage boundary, not an implicit "all platform
logs" claim.

## 5. Log record taxonomy

Every collected first-party record has `time_unix_nano`, `severity_text`,
`service.name`, `service.namespace`, `deployment.environment.name`, an event
name, and a human-readable body. The body is safe to display and is not the
source of machine identity.

Only these low-cardinality attributes are candidate Loki index labels after
review: `service_name`, `service_namespace`, and
`deployment_environment_name` (the OTLP-to-Loki underscore mapping). Severity
is structured metadata initially; promote it only with measured cardinality
evidence.

Structured metadata/body fields may include `trace_id`, `span_id`, `run_id`,
`load_id`, `cycle_id`, snapshot IDs, Kafka topic/partition/offset, object path,
`event.name`, component, error type and safe status. `trace_id`, business keys,
run/load IDs and paths SHALL NOT be labels. Forbidden values include bearer
tokens, passwords, API keys, connection strings, private SQL literals,
customer/PII values, and complete Kafka or request payloads.

## 6. Correlation contract

For a log emitted inside a sampled active span, the record carries the same
32-hex `trace_id` and (when available) `span_id`. Grafana trace-to-logs uses
the existing Tempo datasource and a provisioned Loki datasource. Tempo's
derived query uses `service_name`/`service_namespace` plus a -2s/+2s window;
the LogQL predicate filters structured metadata (`trace_id="..."`), not an
index label. Loki-to-Tempo uses a derived field regex for the 32-hex trace ID
and the Tempo datasource. Both directions must be exercised against the same
trace, not merely two independently healthy datasources.

## 7. Redaction and persistence proof

Redaction occurs before Collector export and is deterministic across stdout and
OTLP. Milestone 2's regression feeds `super-secret-token`, `do-not-store`, a
bearer/password pattern, and the exact SQL literal
`select customer_email from orders`; it queries persisted Loki content through
the Loki HTTP/LogQL API and asserts all forbidden values are absent while
`lakehouse.load_id` and a safe event identity remain. The test must include a
pre-fix failing receipt when a runtime redaction change is made; a Collector
output-only assertion is insufficient.

## 8. Failure, queue and restart semantics

Loki outage, Collector outage, object-store outage, queue saturation and
Collector restart follow NG-0.4's bounded queue/WAL and fail-open semantics:
business processing, stdout and the Prometheus metrics path continue; drops
are observable and bounded. A Loki outage must never make a Kafka consumer,
Spark job, Airflow task or Iceberg commit fail solely due to log export.
Acceptance injects each outage, captures drop/retry/WAL metrics, restarts the
Collector, and proves canonical output is unchanged.

## 9. Resources and CI

M2 measures Loki/Collector RSS and CPU, log bytes/sec, retained bytes, dropped
records, label cardinality, and p95 LogQL latency under the local demo workload.
No production capacity claim is made from this probe. Loki capability CI is a
separate opt-in workflow; core H1 remains Loki-free and must stay green without
either observability profile. The capability workflow records exact SHA, image
digest, profile, retention/storage, redaction and same-trace receipts.

## 10. Preflight classification and hard stops

`PASS_WITH_EXPLICIT_LIMITATIONS`. Native OTLP and a runnable pinned image are
confirmed, and the existing Collector already exposes an OTLP log path. The
remaining work is implementation/evidence: adapters for plain-text emitters,
credentials and isolated storage, finite-retention execution, persisted
redaction, failure injection, resource measurements and CI receipts. Stop if
the chosen storage requires privileged host/Docker access, if native OTLP is
removed from the pinned version, or if Loki failure can block canonical work.
