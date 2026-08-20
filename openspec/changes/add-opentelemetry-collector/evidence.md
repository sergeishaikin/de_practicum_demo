## Milestone 1 preflight receipt

Captured 2026-08-20 on `test/dbt-extensive-testing` at `6d9ad95`.

### Repository recovery

| Check | Command/result |
|---|---|
| Worktree | `git status --short` — clean before this authorised change |
| Baseline | `git branch --show-current` — `test/dbt-extensive-testing`; `git log -3` shows `6d9ad95` at the tip |
| Backlog | `uv run --locked python openspec/backlog/validate_backlog.py` — passed (`14 items`) before promotion |
| Scope | No files under `iceberg/`, `kafka/`, `spark/`, `dags/`, `observability/`, `docker-compose*.yml`, dependency locks or CI changed |

### Read-only compatibility/resource probes

| Probe | Result | Classification |
|---|---|---|
| Docker engine | `docker info` — Engine `29.5.3`, Docker memory `16,627,916,800` bytes | available; no services started |
| Existing Compose graph | `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet` — exit 0 | compatible baseline |
| Root Python environment | `opentelemetry` module not installed (`find_spec` returned `None`) | expected pre-implementation gap; package pinning deferred |
| Cached images | Prometheus/Grafana digests cached; no Collector image cached | no image-size claim; implementation must measure |
| Current client/dependency inputs | `confluent-kafka==2.15.0`; Airflow lock contains OTel API/SDK/exporters `1.44.0` and semantic conventions `0.65b0` | pinning input only; no service consumes it yet |
| Resource baseline | `docs/LOCAL-ENVIRONMENT.md`: 8 CPUs, 15.49 GB Docker memory, idle minimum profile ~0.7 GB | sufficient for a bounded profile probe; measure before adoption |

### Primary-source revalidation

- [Python OTLP exporters](https://opentelemetry.io/docs/languages/python/exporters/)
  documents OTLP HTTP/protobuf and gRPC exporters and a Collector receiver
  configuration.
- [Collector resiliency](https://opentelemetry.io/docs/collector/resiliency/)
  documents bounded sending queues, exponential retry, queue-full and retry
  timeout loss, and `file_storage` WAL with disk-failure limits.
- [Kafka semantic conventions](https://opentelemetry.io/docs/specs/semconv/messaging/kafka/)
  is currently Development and documents `OTEL_SEMCONV_STABILITY_OPT_IN`, so
  convention mode must be pinned and compatibility-tested.
- [Official Collector releases](https://github.com/open-telemetry/opentelemetry-collector-releases)
  lists `otelcol-contrib` as an official distribution and publishes the
  canonical GHCR/Docker image families. The current release observed during
  this freeze is `v0.157.0`; implementation must resolve and record its
  immutable digest rather than use a floating tag.

### M1B backend-contract freeze

| Contract | Frozen decision | Implementation lockout |
|---|---|---|
| Distribution | Official `otelcol-contrib` only | No core, Kubernetes, custom-builder or vendor distribution |
| Image family | `ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.157.0` pending immutable digest capture | No floating tag in merged runtime configuration |
| Receiver/network | OTLP/gRPC on `otel-collector:4317`, 5s app export timeout, no host port; OTLP/HTTP 4318 disabled | No direct app-to-backend endpoint or public OTLP listener |
| Components | `otlp`, `memory_limiter`, `batch`, `filter`/`attributes`, `debug`, `file_storage`, `health_check` | No unreviewed component; specifically no Kafka exporter, host receiver or spanmetrics connector |
| Backend insertion | Collector config/profile only via named `telemetry-backend` exporter slot; debug sink until NG-0.5/0.6 | Applications never gain Tempo/Loki/vendor settings |
| Metric authority | Existing PostgreSQL/Prometheus paths remain authoritative; Collector self-metrics cover only Collector health/pressure | No span-to-SLO/business metric conversion or OTLP migration in NG-0.4 |

This freeze is design/preflight evidence only. The image digest, component
availability in the selected release, and runtime resource measurements remain
Milestone 2 acceptance prerequisites and were not fabricated here.

These sources support the design decisions but do not establish implementation
compatibility for a selected Collector distribution, exporter backend or
Python instrumentation package. Those are Milestone 2 acceptance evidence.

## Preflight classification

**PASS_WITH_EXPLICIT_LIMITATIONS (M1B backend contract frozen; implementation
ready only after a separate grant), with implementation prerequisites.**
No repository or architecture hard stop was found. The existing metrics path,
Kafka partitioning, canonical persistence and engine versions can remain
unchanged. Implementation is still blocked until a subsequent operator grant
authorises Milestone 2 and the implementer pins versions, obtains a compatible
Collector image/distribution, measures resource overhead, and executes the
failure-injection and clean-start gates listed in `tasks.md`.
