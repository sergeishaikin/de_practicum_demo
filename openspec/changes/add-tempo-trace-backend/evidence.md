# Milestone 1 evidence

Captured 2026-09-03 on `feature/ng-0.5-tempo` after M1R reconciliation, with
the repaired exemplar prerequisite and adopted CI receipt in ancestry at
`4931e4c`.

## Recovery and repository inspection

| Check | Result |
|---|---|
| Worktree | Clean before edits; old NG-0.5 branch had no unique commits or uncommitted governed work |
| Baseline | Exact adopted NG-0.4 closure `c151470c`; NG-0.4 `DONE/ADOPTED` |
| Lifecycle | NG-0.5 promoted to `ACTIVE/pending`; NG-0.6 remains `PLANNED/pending` |
| Collector | `telemetry-backend` is the adopted named insertion slot; OTLP/gRPC `otel-collector:4317`; bounded queue/WAL/redaction already governed |
| Existing metrics | Prometheus scrapes writer, medallion, streaming, durable exporter and Collector self-metrics; PostgreSQL/Prometheus remain authority |
| Grafana | Only Prometheus datasource is provisioned; no Tempo datasource or correlation config exists |
| Storage | MinIO currently backs `de-practicum` Iceberg warehouse; no trace bucket/prefix/credential exists |
| Exemplars at original M1 | No exemplar capability existed at `30e7deb`; this was the recorded contradiction |

No service was started, no image was pulled, no bucket or credential was
created, and no canonical data was touched.

## Primary-source revalidation

| Premise | Primary source and current observation | Repository consequence |
|---|---|---|
| Current Tempo release | Official `grafana/tempo` releases list `v3.0.2` as latest stable observed; v3.0 is a breaking architecture/config release | Implementation must pin a verified digest and validate config; no version is frozen in M1 |
| Monolith suitability | Tempo configuration docs describe monolithic `-target=all` with no Kafka; operator docs call monolithic suitable for small/demo/test deployments and non-horizontal | Prefer monolith for opt-in demo; production recommendation remains separate and measured |
| OTLP and storage | Tempo architecture accepts OTLP; S3 docs support S3-compatible stores including MinIO and require explicit backend credentials | Collector-only OTLP route and dedicated object storage are feasible; credentials remain future implementation work |
| Retention/compaction | Tempo configuration/storage docs expose block retention and compaction controls | Values must be finite, paired and measured; defaults are not adopted by assumption |
| TraceQL/search | Tempo/Grafana docs support TraceQL and search by service/span/attributes plus known trace ID | M2 smoke will use stable resource attributes, not ephemeral container names |
| Trace→metrics | Grafana docs state trace-to-metrics uses existing Prometheus-compatible metrics and does not require metrics-generator | One-way correlation can preserve metric authority |
| Metrics→trace | Grafana docs state reverse navigation requires Prometheus exemplars | Original M1 absence was blocking; resolved by `2026-09-03-add-prometheus-trace-exemplars` / adopted receipt `4931e4c` |
| Trace→logs | Grafana docs require both Tempo and Loki-side configuration for bidirectional links | NG-0.5 prepares mapping only; NG-0.6 owns Loki |
| Metrics-generator | Tempo docs describe it as optional and capable of span-metrics/service-graphs; NG-0.4 explicitly locks out span-derived authority | Cannot enable it as an exemplar workaround |

Primary references (accessed 2026-09-03):

- https://github.com/grafana/tempo/releases
- https://github.com/grafana/tempo/blob/main/CHANGELOG.md
- https://grafana.com/docs/tempo/latest/configuration/
- https://grafana.com/docs/tempo/latest/introduction/architecture/
- https://grafana.com/docs/tempo/latest/configuration/hosted-storage/s3/
- https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-metrics/
- https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/

## M1R reconciliation

Archived prerequisite `2026-09-03-add-prometheus-trace-exemplars` has repaired
adopted receipt `4931e4c` (implementation repair
`229882b85eadfcddc5ae31b535b36f9748ac7cc9`) and proves the chosen resolution: bounded application-generated
exemplars on the existing `lakehouse_duration_seconds` Histogram. Its live
proof confirms OpenMetrics output, Prometheus ingestion and unchanged series
labels. The NG-0.4 spanmetrics/metric-authority lockout remains intact.

The former `FAIL_SPEC_CONTRADICTION` is therefore resolved. This M1R changes
design readiness only; it does not implement Tempo, alter Collector routing,
or start NG-0.6.

## Classification

`PASS_WITH_EXPLICIT_LIMITATIONS`: NG-0.5 is ready for a separately authorised
implementation milestone. Tempo image/config compatibility, isolated storage,
retention/resource measurements, failure injection and final Grafana↔Tempo
correlation remain M2 acceptance work. NG-0.5 stays `ACTIVE/pending`.

`READY FOR NG-0.5 IMPLEMENTATION: YES` means the M1 design gate is satisfied;
it does not authorise M2 or any Tempo runtime change.
