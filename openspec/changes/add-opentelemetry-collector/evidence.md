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

## Milestone 2 implementation receipt

Captured 2026-08-20 on the authorised `feature/ng-0.4-otel` worktree from the
M1B frozen baseline `33dd4b23af57b3a917f992800c99d501c9d697bf`.

### Pinned runtime and contract checks

| Check | Result |
|---|---|
| Collector image | `ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib@sha256:f2f01157055a9b2aab9df7118e1f1c9abf345e99b23bc7a2bc791db374a7d0f6`; `docker buildx imagetools inspect` matched the digest |
| Collector config | `docker run --rm -v observability/otel:/etc/otelcol-contrib:ro <image> validate --config=/etc/otelcol-contrib/collector-config.yaml` — passed |
| Standalone Collector | v0.157.0 started with health check, OTLP/gRPC receiver, file storage and debug pipelines; log reported `Everything is ready` |
| Compose graph | Base and `--profile otel` graphs both passed `docker compose ... config --quiet`; profile is opt-in and has no host OTLP port |
| Locked Python dependencies | `uv pip compile --universal --generate-hashes --python-version 3.12` regenerated Iceberg, observability and Kafka producer locks with OTel packages at `1.44.0` |
| Focused tests | `uv run --locked pytest tests/test_otel_contract.py tests/test_observability.py -q` — passed (optional root-environment OTel round-trip skipped when OTel is not installed) |
| Static gates | Ruff, Black and mypy passed for changed Python modules; Compose/config and Collector validation passed |
| Application smoke | Writer and observability service images loaded the pinned OTel SDK; `OTEL_ENABLED=1` created providers and exporter shutdown remained fail-open when no Collector endpoint was available |

### Instrumentation and safety boundaries

Writer, medallion and the polling observability exporter now emit opt-in
traces/logs with stable service resources. The Kafka producer injects W3C
`traceparent` headers without changing payload, key or partition behavior; the
propagation helper preserves unrelated headers and ignores duplicate context
keys. Collector redaction blocks credential-like keys and bearer values,
attributes are bounded, and file-storage WAL is confined to the Collector
volume. Existing PostgreSQL/Prometheus metric authority is unchanged. No
Kafka exporter, spanmetrics connector, direct application backend, canonical
sink, Spark/Airflow version change or schema/partition change was introduced.

### Explicitly unclaimed acceptance gates

Tasks 2.6 and 2.7 remain open. No outage/queue-overflow/WAL recovery or
canonical-output-parity test was claimed because the frozen M1B contract has no
authorised backend and this implementation does not start the full live stack.
No CPU/RSS/disk/throughput baseline or dashboard/alert change was claimed;
those require a dedicated CI/live acceptance window. Task 2.8 records the
focused/config gates completed here while clean-start and existing
Prometheus/Grafana gates remain acceptance work. The repository-wide pytest
attempt was not claimed as a pass: after the focused and baseline-contract
tests passed, the run became environment-level unresponsive and timed out with
an `OSError: [Errno 22] Invalid argument` while flushing captured stdout.

## Current classification

**IMPLEMENTED_WITH_EXPLICIT_LIMITATIONS (Milestone 2).** The opt-in Collector
profile, first-party instrumentation, W3C producer propagation, redaction,
bounded queues/WAL and locked dependencies are implemented and statically
validated. Failure-injection, resource-overhead and live clean-start gates are
intentionally deferred to the acceptance window recorded in `tasks.md`.

## Milestone 2B acceptance receipt

Captured 2026-08-21 on `feature/ng-0.4-otel`, after operator continuation from
`94ea6a222fd46aba7280377c10fafe4a9df260c3`. The acceptance sink is strictly
test-only: `tests/otel_acceptance.py` generates temporary source/sink Collector
configs, starts disposable Contrib containers on an isolated Docker network,
and removes the containers, network and temporary WAL directories in `finally`.
The committed production Collector remains debug-only; no product backend,
application endpoint, schema, persistence or engine version changed.

### Deterministic OTLP network receipt

Command: `uv run --locked python tests/otel_acceptance.py`.

| Scenario | Receipt |
|---|---|
| Config/image validation | Source and sink temporary configs validated by the pinned `otelcol-contrib` digest (`sha256:f2f011...a7d0f6`). |
| Normal delivery | Disposable sink Prometheus self-metric `otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"} 8`; source exporter sent 8 spans. |
| Sink outage/retry | Sink stopped; 64 spans emitted while source exporter retry/WAL remained active; source receiver accepted 72 total and no receiver refusals were reported. |
| Collector restart/WAL | Source restarted with the same temporary bind-mounted WAL; source exporter later reported 66 sent spans after sink recovery. |
| Recovery drain | Recreated sink accepted 66 spans (the 64 outage spans plus the 2 post-recovery spans), proving network delivery after restart. |
| Queue/pressure metrics | Source reported queue capacity 4 for traces/logs and queue size 0 at the post-export snapshots; no drop/refusal counter was observed in this WAL-backed run. A finite-queue drop-mode run remains open. |
| Resource receipt | Baseline had no acceptance Collector containers; source/sink at receipt were 35.57 MiB/33.86 MiB and 0.08%/0.45% CPU; source WAL footprint was 98,304 bytes. These are dated observations, not thresholds. |

The first harness attempt failed before telemetry delivery because the
temporary app used a `source` hostname without declaring a Docker network
alias. This was a harness-only wiring defect; the explicit `source`/`sink`
aliases were added and the bounded rerun above passed. No production behavior
was changed to fix it.

### Canonical and repository gates

`uv run --locked pytest tests/test_new_baseline_contract.py tests/test_otel_contract.py tests/test_observability.py tests/test_ops.py tests/test_order_contract.py -q` passed (47 passed, 1 skipped). The coverage completion gate
`uv run --locked pytest tests --cov=iceberg --cov-report=term-missing
--cov-fail-under=90` passed (511 passed, 1 skipped, 81 deselected; 93.22%).
The latest plain `uv run --locked pytest -q` invocation was intentionally
aborted by the operator shortly after start, so the full repository test gate
is **UNRESOLVED**, not a pass. The earlier M2 attempt had timed out while
flushing captured stdout with `OSError: [Errno 22] Invalid argument`; the
focused and coverage runs now complete normally, narrowing the prior issue to
that uncompleted invocation rather than claiming a root cause.

Ruff, Black, mypy, Compose base/profile config, Collector validation, backlog
validation and `git diff --check` remain required static/config receipts. No
spanmetrics, direct backend, Prometheus/PostgreSQL authority change or
dashboard/alert ownership change was introduced.

### M2B classification

**PARTIAL.** Normal OTLP delivery, sink outage/retry, bounded WAL restart and
recovery drain are evidenced. Finite-queue saturation/drop, retry-horizon loss,
canonical output parity as an M2B live assertion, and the plain full-repository
pytest gate remain unresolved for the dedicated final CI/live acceptance
window. NG-0.4 is not ready for archive.

## Milestone 2C final local acceptance receipt

Captured 2026-08-21 after the M2B checkpoint. The same disposable harness was
extended only with temporary acceptance configurations; the committed runtime
config remains unchanged.

### Tiny-queue and retry-horizon probe

The temporary source config set `queue_size: 1`, removed `file_storage` from
the exporter queue, and set `max_elapsed_time: 2s`. With the sink absent, 128
spans were emitted. Pinned Collector self-metrics reported:

```text
otelcol_exporter_queue_capacity{data_type="traces",exporter="otlp/acceptance"} 1
otelcol_exporter_send_failed_spans{exporter="otlp/acceptance",server_address="sink",server_port="4317"} 128
otelcol_exporter_sent_spans{exporter="otlp/acceptance",server_address="sink",server_port="4317"} 0
otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"} 128
otelcol_receiver_refused_spans{receiver="otlp",transport="grpc"} 0
```

This proves the bounded retry horizon and exporter-send failure accounting;
`send_failed_spans` is deliberately not relabelled as queue enqueue/drop
failure. No positive `enqueue_failed`/drop/refusal metric appeared, so finite
queue saturation/drop is not claimed complete.

### Canonical parity and resource observations

The same fixed canonical payload hash was produced by the disposable workload
with telemetry OFF, telemetry ON with the sink up, and telemetry ON while the
sink was stopped:

```text
65af0370d3687a0d5354fcacae3e612d63f77fd7810f050a42a9c9713e56d5c2
```

This is a bounded disposable workload probe only; it does not establish
production canonical-output parity. It does not alter schemas, partitioning,
persistence or engine versions. M2B's same-run Collector observations remain
the only resource receipt: source/sink RSS 35.57/33.86 MiB, CPU 0.08%/0.45%,
and source WAL 98,304 bytes versus no acceptance Collector containers at
baseline. A controlled equal-throughput OFF/ON CPU/RSS/disk delta is not
claimed, and no dashboard/alert ownership changed.

### Prometheus visibility

A temporary Prometheus instance using the worktree's committed
`observability/prometheus/prometheus.yml` discovered the `otel-collector:8888`
target on `de_demo_net`; the target remained `unknown` during the short probe
because the disposable Collector was removed with the harness before a healthy
scrape receipt. Direct Collector self-metrics were verified by the harness,
but Prometheus/Grafana operational visibility for queue/capacity/failure/drop/
receiver signals is therefore unresolved locally (no spanmetrics or new
authority was added).

### M2C classification

**PARTIAL.** Retry-horizon loss accounting and a bounded OFF/ON/outage canonical
hash probe are evidenced; production canonical-output parity is unresolved.
Finite queue drop/refusal, equal-workload resource delta, healthy Prometheus
scrape, and the plain full-repository pytest run remain open.
Task 2.6 remains unchecked; Task 2.7 remains unchecked. NG-0.4 is not ready for
final CI/archive.

## Milestone 2D closure-blocker receipt

Captured 2026-08-21 after the M2C checkpoint. This receipt corrects the
M2C queue false positive without changing production configuration.

### Queue saturation/drop distinction

The disposable pressure config now sets `queue_size: 1`, removes queue WAL,
sets `send_batch_size: 1` and `send_batch_max_size: 1`, and keeps the 2-second
retry horizon. Its pinned v0.157.0 self-metrics after 128 received spans were:

```text
otelcol_exporter_enqueue_failed_spans{exporter="otlp/acceptance"} 127
otelcol_exporter_send_failed_spans{exporter="otlp/acceptance",server_address="sink",server_port="4317"} 1
otelcol_exporter_sent_spans{exporter="otlp/acceptance",server_address="sink",server_port="4317"} 0
otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"} 128
otelcol_receiver_refused_spans{receiver="otlp",transport="grpc"} 0
```

This is a bounded saturation/drop PASS for the disposable acceptance config;
the retry/send failure is recorded separately. `tests/test_otel_contract.py`
contains a regression test proving a `send_failed_spans`-only sample is not
classified as queue drop while an `enqueue_failed_spans` sample is. The
production queue remains unchanged.

### Remaining closure blockers

The OFF/ON/outage canonical hash probe remains a disposable harness probe, not
production repository data-path parity. Equal-workload OFF/ON CPU/RSS/disk/
throughput deltas remain unmeasured. A temporary Prometheus instance discovered
the committed `otel-collector:8888` target, but its health remained `unknown`
before disposable cleanup; healthy scrape and Grafana datasource validity are
not claimed. The one canonical full `uv run --locked pytest -q` attempt from a
clean state was aborted by the operator, so the full repository pytest gate is
UNRESOLVED. Tasks 2.6 and 2.7 remain open.

### M2D classification

**PARTIAL.** Queue saturation/drop and retry-horizon self-metrics are now
correctly evidenced and the false-positive detector has regression coverage.
Production canonical parity, resource delta, healthy Prometheus/Grafana
visibility and the full repository pytest gate remain closure blockers.

## Milestone 2E final closure receipt

Captured 2026-08-21 after the M2D checkpoint. Queue saturation/drop remains
closed by M2D and is not reopened here.

### Prometheus and Grafana

A temporary Prometheus instance used the committed worktree
`observability/prometheus/prometheus.yml` and a temporary Collector with a
writable test WAL bind on the existing `de_demo_net`. The actual target was
healthy:

```text
job=otel-collector instance=otel-collector:8888 health=up
otelcol_process_uptime{instance="otel-collector:8888",job="otel-collector"} 11.722849719
```

A temporary Grafana instance using the committed datasource provisioning
returned datasource health `status=OK` and its `/api/ds/query` response returned
the same `otelcol_process_uptime` series from Prometheus. This is a PASS for
committed Prometheus scrape and Grafana datasource/query validity; no
spanmetrics or alternate metric authority was introduced.

### Production-path and resource blockers

The running repository stack binds application code from the separate root
worktree (`C:\Code\de_practicum_demo\de_practicum_demo\iceberg`), while this
feature worktree is `C:\Code\de_practicum_demo\ng04-otel`. The root stack's
Collector profile is disabled and its application telemetry is OFF. Running
the feature-worktree writer/medallion against the existing state would require
a cutover/rebuild owned by H1; a destructive fresh-volume rebuild is explicitly
out of scope here. Therefore a real production repository data-path
OFF/ON/outage canonical-output comparison was not executed and is not claimed.
The disposable equal-hash probe remains only diagnostic evidence.

For the same reason, no equal-workload OFF/ON duration/throughput/app
CPU/RSS/Collector CPU/RSS/WAL delta was measured. M2B's bounded Collector
observation (RSS 35.57/33.86 MiB, CPU 0.08%/0.45%, WAL 98,304 bytes) remains a
local-demo observation, not a production delta or threshold claim.

### Canonical full repository gate

From a clean state with no pytest processes or temporary M2E containers, the
exact required command `uv run --locked pytest` passed:

```text
512 passed, 1 skipped, 81 deselected in 25.27s
```

### M2E classification

**PARTIAL.** Prometheus/Grafana visibility and the exact full repository pytest
gate pass. Production canonical parity and equal-workload resource delta fail
because the safe local path is the separate root-worktree stack and H1-owned
clean-start/cutover work is not authorised here. Tasks 2.6 and 2.7 remain open;
NG-0.4 is not ready for archive.

## Milestone 3A authoritative H1 acceptance receipt

Captured 2026-08-21 from the latest successful H1 workflow run
`32472427743` at exact feature SHA
`3448287803b08283f543007413c20a725dd2e582`.
The baseline clean-stack job was `96741823243`; the separate OTel acceptance
job was `96741823461`. The uploaded artifact was
`ng04-otel-acceptance-evidence` (artifact ID `9443466762`). This receipt
supersedes the earlier run `32471367218`, whose OFF workload passed but whose
receipt helper imported an unavailable DB adapter before the AST-only helper was
deployed.

### H1 clean-stack and production workload parity

| Check | Result |
|---|---|
| Exact checkout | OTel job checked out and verified the feature SHA above |
| Clean-stack baseline | PASS: build, bootstrap, integration, deterministic E2E, dbt semantic contract, Prometheus/Grafana smoke and volume cleanup |
| Canonical contract | `total_events=101`, `landing_rows=99`, `bronze_rows=99`, `silver_rows=95`, `duplicates_removed=4`, `total_violations=7`, `gold_row_count=11`, `total_revenue=672.0` |
| Canonical contract hash | `e3a84657087125c8e9a1559ee4a5620e704a98c61592954da9b78dd05dfcce20` in OFF, ON and Collector-outage receipts |
| OFF workload | JUnit PASS; 119.22s |
| ON workload | JUnit PASS; 113.76s |
| Collector outage | Collector stopped; JUnit PASS and canonical parity retained; 117.59s |

The OFF, ON and outage runs execute the authoritative repository E2E fixture
through Kafka, Spark streaming, Iceberg writer/medallion and Trino/PostgreSQL
assertions. The equal canonical contract hash is therefore production-path
parity, not the earlier disposable-harness hash probe.

### Telemetry visibility and resource receipt

The healthy ON phase passed the Collector Prometheus target check
(`otel-collector` UP), queried `otelcol_process_uptime`, and passed Grafana
health and provisioned Prometheus datasource checks. The outage phase stopped
the Collector and still passed the canonical E2E workload; cleanup removed
the acceptance volumes.

Each phase recorded Collector WAL bytes before/after (`4096`/`4096`) and
point-in-time CPU/RSS snapshots for `orders-streaming`, `iceberg-writer`,
`iceberg-medallion` and `otel-collector`, alongside the equal-workload
durations above. Resource classification is **PASS_WITH_EXPLICIT_LIMITATIONS**:
GitHub-hosted runner snapshots are noisy point samples rather than a
repeatable capacity threshold or continuous profile, but the accepted NG-0.4
contract (record CPU/RSS, queue/WAL disk use and workload throughput without
changing existing Prometheus/Grafana ownership) is reconciled. No dashboard,
alert or metric-authority change was introduced.

### M3A classification

**PASS_WITH_EXPLICIT_LIMITATIONS.** H1 clean-start, production canonical
OFF/ON/outage parity, healthy telemetry visibility, outage fail-open behavior,
resource receipts and the exact full repository gate are complete. The
resource receipt carries the GitHub-runner limitation above and makes no
unsupported overhead threshold claim. NG-0.4 remains unarchived and no NG-0.5
work is started by this receipt.

## Milestone 3B authorization history

The original lifecycle grant remains `operator:explicit-ng-0.4-milestone-1`;
it is not replaced or renamed. The operator subsequently gave explicit
continuations for bounded Milestone 2 acceptance, Milestone 3A H1 acceptance,
and, in the 2026-08-21 instruction authorizing this sequence, final NG-0.4
adoption, CI and archive. No separate authorization identifier was supplied
for those continuations, so this record deliberately uses their dated
operator instructions rather than inventing IDs. The continuation remains
scoped to NG-0.4 and does not authorize NG-0.5/0.6/0.7 or any backend,
spanmetrics or metric-authority change.

### M3B pre-archive local gate receipt

On the docs-only descendant of the accepted runtime, the required local gates
passed before the PRE_ARCHIVE_SHA was pushed:

| Gate | Result |
|---|---|
| Exact repository pytest | `uv run --locked pytest` — 512 passed, 1 skipped, 81 deselected in 24.36s |
| Ruff | `uv run --locked ruff check .` and DAG AIR3 preview — passed |
| Black | `uv run --locked black --check .` — 100 files unchanged |
| Mypy | `uv run --locked mypy` — no issues in 10 source files |
| Compose | Base and `--profile otel` config quiet validation — passed |
| Collector | Pinned Contrib config validation — passed |
| Backlog | `uv run --locked python openspec/backlog/validate_backlog.py` — 14 items, passed |

The first scoped mypy probe against individual directories was not used as a
gate because it bypassed the repository's declared `pyproject.toml` typed
scope and reported missing optional imports; the exact CI command above passed.
