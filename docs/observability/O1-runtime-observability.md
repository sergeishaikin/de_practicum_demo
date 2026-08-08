# O1 — Lakehouse Runtime Observability

Status: **implemented and verified**.

O1 adds Prometheus and Grafana around the existing lakehouse runtime. It does
not change Silver or Gold ownership, B2 projection logic, progress state, D-3a
physical layout, or writer concurrency.

## Ownership

| Signal | Owner | Role |
|---|---|---|
| Writer and medallion live metrics | application process via `iceberg/common/ops.py` | direct operational time series |
| Spark streaming metrics | `spark/jobs/orders_streaming.py` | direct streaming activity and DLQ signals |
| Maintenance status | `observability/postgres_exporter.py` | projection of durable maintenance audit |
| `marts.lakehouse_metrics` | PostgreSQL | durable operational/audit history |
| Prometheus | `prometheus` service | scrape, retention, rules, alerts |
| Grafana | `grafana` service | provisioned dashboard presentation |

PostgreSQL remains the evidence/history store. Prometheus is not a replacement
for the existing `Metrics.record()` path.

## Runtime topology

```text
writer :9101 ───────┐
medallion :9102 ────┤
Spark :9103 ────────┼──> Prometheus :9090 ──> Grafana :3000
PG exporter :9104 ──┘
        │
        └── marts.lakehouse_metrics / marts.maintenance_runs
```

The Prometheus and Grafana data volumes are persistent. Grafana datasource,
dashboard provider, dashboard JSON, and Prometheus rules are all stored in the
repository and provisioned at startup.

## Dashboard layout

`Lakehouse Runtime` has four explicit sections:

1. **Pipeline Health** — application events by status and durable source availability.
2. **Progress & Recovery** — available/in-flight/completed work and maintenance health.
3. **Correctness** — FF-14, shadow, lower-version, quality, and Spark DLQ signals.
4. **Performance** — Silver/Gold duration, processed keys/rows/files, and file/byte amplification.

## Alert semantics

Alerts are intentionally tied to actionable conditions:

- unresolved in-flight work with no recent medallion event for ten minutes;
- any FF-14 conflict;
- any shadow mismatch;
- application failures in the recent ten-minute window;
- unhealthy latest maintenance audit.

No arbitrary throughput or CPU thresholds are included. O1 does not add
tracing, Loki, Tempo, OpenTelemetry, or production deployment hardening.

## Metric contract

Writer and medallion expose `lakehouse_events_total`, `lakehouse_work`,
`lakehouse_correctness_total`, `lakehouse_stage_duration_seconds`,
`lakehouse_processed`, `lakehouse_files`, and `lakehouse_bytes`. Spark exposes
`spark_batches_total`, `spark_valid_events`, `spark_dead_letter_events_total`,
`spark_query_up`, and `spark_last_batch_id`.

## Verification evidence

Verification evidence:

- Ruff: passed;
- focused observability tests: `25 passed`;
- full fast suite: `107 passed, 30 deselected`;
- Compose config: passed;
- Prometheus `promtool check config`: passed;
- Prometheus `promtool check rules`: 5 rules passed;
- live scrape: 4/4 Prometheus targets healthy;
- live metric query: writer, medallion, Spark, and maintenance series present;
- Grafana `/api/health`: database `ok`;
- provisioned dashboard: `Lakehouse Runtime`, 10 panels, repository-backed.

D-3a remains explicitly deferred and can only be reconsidered using the
resulting telemetry.
