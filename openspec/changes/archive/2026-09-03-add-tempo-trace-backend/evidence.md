# Milestone 1 evidence

> Historical status notice: sections below preserve lifecycle state at each
> milestone capture. The **Final adoption and archive** section is authoritative
> for the concluded NG-0.5 state.

Captured 2026-09-03 on `feature/ng-0.5-tempo` after M1R reconciliation, with
the repaired exemplar prerequisite and adopted CI receipt in ancestry at
`5644c49`.

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
| Current Tempo release | Official GitHub release API reports `v3.0.3`, published 2026-08-13; v3.0 is a breaking architecture/config release | M2 pins and verifies the v3.0.3 digest and config |
| Monolith suitability | Tempo configuration docs describe monolithic `-target=all` with no Kafka; operator docs call monolithic suitable for small/demo/test deployments and non-horizontal | Prefer monolith for opt-in demo; production recommendation remains separate and measured |
| OTLP and storage | Tempo architecture accepts OTLP; S3 docs support S3-compatible stores including MinIO and require explicit backend credentials | Collector-only OTLP route and dedicated object storage are feasible; credentials remain future implementation work |
| Retention/compaction | Tempo configuration/storage docs expose block retention and compaction controls | Values must be finite, paired and measured; defaults are not adopted by assumption |
| TraceQL/search | Tempo/Grafana docs support TraceQL and search by service/span/attributes plus known trace ID | M2 smoke will use stable resource attributes, not ephemeral container names |
| Trace→metrics | Grafana docs state trace-to-metrics uses existing Prometheus-compatible metrics and does not require metrics-generator | One-way correlation can preserve metric authority |
| Metrics→trace | Grafana docs state reverse navigation requires Prometheus exemplars | Original M1 absence was blocking; resolved by `2026-09-03-add-prometheus-trace-exemplars` / adopted receipt `5644c49` |
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
adopted receipt `5644c49` (implementation repair
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

## Milestone 2 implementation and pre-adoption evidence

Captured 2026-09-03 from the bounded `feature/ng-0.5-tempo` worktree. This
section is an implementation receipt only; the change is intentionally not
archived and NG-0.5 remains `ACTIVE/pending`.

### Version and configuration

| Check | Receipt |
|---|---|
| Tempo release | `v3.0.3`, published 2026-08-13; verified from the official GitHub release API |
| Tempo image | `grafana/tempo@sha256:0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5`; `--version` reported revision `1900ed7bb` |
| Tempo mode | `target: all` monolithic opt-in profile; no Kafka and no metrics-generator/spanmetrics block |
| Config gate | `docker run ... --config.file=/etc/tempo.yaml --config.expand-env=true --config.verify=true` exited 0 |
| Storage | dedicated `tempo-minio`, `de_demo_tempo_minio_data`, Tempo WAL/data volume, bucket `tempo-traces`, prefix `ng05/` |
| Retention | block retention 24h, compacted block retention 1h, compaction window 1h; MinIO lifecycle expires `ng05/` after 2 days |
| Resource bounds | Tempo `mem_limit: 768m`, `cpus: 1.0`; Collector memory limiter 256 MiB and queue size 256 |
| Disk/object receipt | `docker stats` showed Tempo `23.7MiB / 768MiB`; MinIO `mc du` reported `658KiB / 23 objects` under `tempo-traces/ng05/`; the mounted Tempo volume was `4096` bytes at the probe boundary |

### Live OTLP, TraceQL and correlation proof

The disposable first-party image `de-practicum-demo-iceberg:0.11.1-h1` used the
existing `common.telemetry.setup_telemetry("iceberg-writer")` and
`common.ops._RuntimeMetrics` code. It sent one sampled span through
`otel-collector:4317`, observed `lakehouse_duration_seconds`, and stayed alive
only for the bounded probe. The live receipt from
`uv run --locked python tests/tempo_acceptance.py` was:

```json
{"load_id":"ng05-m2-exemplar-acceptance","prometheus_exemplar_match":true,"service":"iceberg-writer","tempo_ready":true,"trace_id":"935046e21dd4db55dc9941cb4147b3bf","traceql_match":true}
```

The same trace ID was returned by `GET /api/traces/{trace_id}`, Tempo TraceQL
search `q={ .lakehouse.load_id = "ng05-m2-exemplar-acceptance" }`, and
Prometheus `GET /api/v1/query_exemplars?query=lakehouse_duration_seconds_bucket`.
The exemplar remained correlation metadata and did not become a metric series
label. Grafana provisioning exposes stable UIDs `prometheus` and `tempo`,
`tracesToMetrics`, and the Prometheus `exemplarTraceIdDestinations` mapping;
there is no Loki datasource or `tracesToLogsV2` configuration.

### Queue, outage and canonical-path receipts

The existing NG-0.4 disposable harness passed after the Tempo route was added:
`normal_received_spans=8`, `recovered_received_spans=66`, and the bounded
pressure run reported `otelcol_exporter_enqueue_failed_spans{exporter="otlp/acceptance"}
127` while `otelcol_receiver_refused_spans` remained 0. Its canonical payload
hash was unchanged with telemetry disabled, enabled, and during the injected
sink outage (`65af0370d3687a0d5354fcacae3e612d63f77fd7810f050a42a9c9713e56d5c2`).

Tempo restart and MinIO outage were exercised with the named optional services
only; the Collector and canonical MinIO remained separate. A positive MinIO
receipt showed objects under `ng05/` and lifecycle rule `prefix ng05/`, while
the Tempo credentials could not write to the canonical `minio` endpoint. No
canonical warehouse object, Kafka payload, partitioning, or application metric
schema was changed.

### Focused gates and CI

Passed locally:

```text
uv run --locked pytest -q tests/test_tempo_contract.py tests/test_otel_contract.py
8 passed, 1 skipped
uv run --locked python tests/otel_acceptance.py
normal_received_spans=8; recovered_received_spans=66; pressure enqueue failures=127
uv run --locked python tests/tempo_acceptance.py
tempo_ready=true; traceql_match=true; prometheus_exemplar_match=true
```

`.github/workflows/ci-ng05-tempo.yml` is a separate capability workflow. It
renders and verifies the pinned Tempo config, starts only the optional Tempo /
Collector capability plus a disposable Prometheus authority, runs both
acceptance harnesses and captures/uploads diagnostics on failure. Core H1 CI does not depend on the
profile. This receipt is not an archive or DONE transition.

The latest executed capability receipt is run [33807398167](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33807398167),
head SHA `4c6108f84d55f8c5e22cde9fa5eaf16a95fe420f`. Its job passed pinned
configuration verification, optional profile startup, disposable Prometheus and
Grafana startup, focused contracts, live Tempo acceptance, and the Tempo/MinIO
stop/restart and object-store outage probes. Earlier successful run
`33803155411` tested the predecessor runtime SHA before this repair; it is
retained as historical evidence, not used as the current closure receipt.

Repository-wide Ruff and Black gates passed, and the full unit suite passed
`522 passed, 1 skipped, 81 deselected`. The required completion command
`uv run --locked mypy` passes (`Success: no issues found in 10 source files`).
The earlier path-explicit diagnostic (`mypy iceberg kafka/producer tests`) is
outside the configured completion command and reports unrelated optional-stub
and duplicate-module errors; it is not used as the M2 gate.

The closure-only live regression now also proves `trace_redaction=true`: a
controlled span containing authorization/password values and a SQL statement
is stored with forbidden values masked while `lakehouse.load_id` remains
queryable. The same run reports `storage_positive=tempo-traces/ng05/isolation-proof`
and `storage_negative=DENIED canonical/iceberg-ng05-denied`, using a disposable
canonical MinIO endpoint and no warehouse data.

The M2C storage repair supplies the actual `TEMPO_S3_ACCESS_KEY` and
`TEMPO_S3_SECRET_KEY` from the runtime environment (or `.env`) to both probes.
The positive and negative commands use the same credentials and assert their
process return codes; no credential or command output is printed. A live local
receipt passed with the configured `tempo-demo` credentials.

For the required redaction regression, baseline source SHA `941eec1` had the
traces pipeline `processors: [memory_limiter, batch]`. A disposable Collector
with that pre-fix pipeline received the controlled span and Tempo trace
`8cdca7a2a009343e08bb2fe8af06f108` retained all three forbidden values:
`Bearer super-secret-token`, `do-not-store`, and
`select customer_email from orders`; the acceptance exited 1 with
`forbidden trace attribute survived redaction`. After the repaired pipeline,
trace `f9d2a35beb972b5d7f2f4eb559c20cf9` masked all three values while
preserving `ng05-m2-exemplar-acceptance` and the acceptance exited 0.

Grafana 11.2 was started with the real provisioning directory. Its health and
both datasource UIDs were checked, then Grafana's datasource proxy returned the
same Tempo trace ID and the same Prometheus exemplar trace ID. The receipt is
`grafana_correlation=true`, not merely a static YAML assertion.

The capability workflow now performs a Tempo stop/readiness failure, restart
readiness recovery, MinIO stop while Tempo remains running, and MinIO restart
readiness recovery. These are bounded probes; canonical H1 remains a separate
workflow.

The exact-SHA core H1 receipt for the repaired runtime is run
[33807455038](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33807455038),
head SHA `4c6108f84d55f8c5e22cde9fa5eaf16a95fe420f`. Both jobs passed: the
H1-owned clean OFF/ON/Collector-outage parity phases and the fresh-volume baked
runtime full verification (integration, deterministic E2E, dbt semantic
contract, Prometheus/Grafana smoke, runtime evidence, and cleanup).

## Milestone 2 classification

`PASS_WITH_EXPLICIT_LIMITATIONS`: bounded implementation, local gates,
capability CI and exact-SHA core H1 all pass. The only remaining limitation is
governance: final adoption/archive is intentionally withheld pending explicit
user approval; NG-0.5 remains `ACTIVE/pending`.

## Final adoption and archive

The explicit final adoption authorization was received after the M2C receipts.
Pre-adoption HEAD was `ca33344b2694bff0292207004b16cb31048eac17`; the accepted
runtime SHA was `4c6108f84d55f8c5e22cde9fa5eaf16a95fe420f`, covered by capability
run `33807398167` and core H1 run `33807455038`. This change was then adopted
into `openspec/specs/tempo-trace-backend/spec.md` and archived here. NG-0.5 is
`DONE / ADOPTED`; NG-0.6 remains `PLANNED / pending` and unauthorised.

### Post-archive CI

All applicable final workflows were dispatched against closure SHA
`eb869eed8fcbaae62a441cba28bf53276e3c0ae3`:

| Workflow | Run | Result |
|---|---|---|
| M5 architecture gates | [33810350355](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33810350355) | success |
| NG-0.5 Tempo capability | [33810355152](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33810355152) | success |
| H1 clean reproducible stack (rerun) | [33810352974](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33810352974) | success; both jobs green |

The repository `CI` workflow has no `workflow_dispatch` trigger and only runs
for `main` pushes or pull requests; its exact local completion equivalent was
run before archive (Ruff, Black, mypy, full pytest and coverage). No S1/dbt or
metadata-specific workflow was applicable to this documentation-only archive
transition.
