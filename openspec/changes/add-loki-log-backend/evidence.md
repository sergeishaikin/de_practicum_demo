# Evidence: NG-0.6 Milestone 1

## Recovery receipt

- Worktree: `C:\Code\de_practicum_demo\ng06-loki`
- Branch: `feature/ng-0.6-loki`
- Baseline: `07b475fd28a831794d817580c1dee09c56d098b9`
- Programme baseline branch: `test/dbt-extensive-testing`
- `git status --short`: clean before artifact creation
- No runtime, Compose, Collector, Grafana, dependency or CI implementation was changed.

## Exact baseline H1

Run `33869184341` targets the exact baseline SHA above and completed
**SUCCESS**. Both jobs succeeded: OTel parity/Collector-outage phases and
fresh-volume full verification (integration, deterministic E2E, dbt semantic
contract, Prometheus/Grafana smoke, runtime evidence and teardown).
Workflow URL:
https://github.com/sergeishaikin/de_practicum_demo/actions/runs/33869184341.

## Primary-source revalidation

- [Grafana Loki latest release](https://github.com/grafana/loki/releases/latest):
  v3.7.7, released 2026-08-27, revision `7a40404`.
- [Loki native OTLP ingestion](https://grafana.com/docs/loki/latest/send-data/otel/):
  use Collector `otlphttp` to `/otlp`; enable structured metadata; review
  default resource-label promotion.
- [Structured metadata](https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/):
  schema >=13/TSDB, high-cardinality fields as metadata, size/entry limits.
- [Loki retention](https://grafana.com/docs/loki/latest/operations/storage/retention/):
  Compactor-managed finite retention, 24h index period, scoped lifecycle.
- [Loki storage](https://grafana.com/docs/loki/latest/configure/storage/):
  labels index, content in chunks/object store; TSDB/Compactor recommended.
- [Grafana trace-to-logs](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/):
  both Tempo and Loki datasource configuration and shared identifiers are
  required for navigation.

## Bounded local probes

Executed without starting a persistent service:

```text
docker buildx imagetools inspect grafana/loki:3.7.7
→ manifest sha256:d70e4659623f3e109af669cae76fe2a5dd5be54e2298fe8aed380d982fbc2500

docker run --rm --entrypoint /usr/bin/loki \
  grafana/loki@sha256:d70e4659623f3e109af669cae76fe2a5dd5be54e2298fe8aed380d982fbc2500 -version
→ loki, version 3.7.7; revision 7a40404f; linux/amd64
```

These probes establish image compatibility only. They are not a Loki
acceptance run and provide no retention, redaction, storage-isolation or
failure evidence.

## Preflight

`PASS_WITH_EXPLICIT_LIMITATIONS` — design may proceed to implementation after
explicit Milestone 2 authorisation. Milestone 1 stops here.
