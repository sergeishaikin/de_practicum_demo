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

`PASS_WITH_EXPLICIT_LIMITATIONS` — design proceeded only after the separate
explicit Milestone 2 authorisation recorded in the operator checkpoint.

## Milestone 2 implementation and local acceptance receipt

- Commit ancestry: implementation is based on authorised M1 `6a2be13` and
  exact programme baseline `07b475f`.
- Loki image: `grafana/loki@sha256:d70e4659623f3e109af669cae76fe2a5dd5be54e2298fe8aed380d982fbc2500`
  (v3.7.7, revision `7a40404f`).
- Compose rendered with `--profile '*'`: PASS.
- Loki config `--verify-config=true`: PASS.
- `tests/test_loki_contract.py`, Tempo and OTel contracts: 12 passed, 1 skipped.
- Live `tests/loki_acceptance.py`: PASS. Final fresh-volume run used same trace ID
  `3d6ee23371a4efe68fac7f7a0c9f3568`; persisted LogQL query returned the
  record, retained `ng06-loki-load-001`, and rejected
  `super-secret-token`, `do-not-store`, and the sensitive SQL literal.
- Fresh-series inspection after the explicit OTLP resource-label allow-list
  fix returned only `service_name`, `service_namespace`, and
  `deployment_environment_name`; `service_instance_id` and trace identifiers
  were not indexed.
- Storage permissions: positive write to `loki-logs/ng06/storage-proof`;
  negative write to canonical MinIO was denied using the same Loki credentials.
- Loki outage/restart: Collector remained healthy and canonical MinIO remained
  running while Loki was stopped; Loki returned HTTP 200 `/ready` after restart.
- Grafana proxy query: provisioned Loki datasource UID `loki` returned one
  result for the same trace ID through `/api/datasources/proxy/.../loki/api/v1/query_range`;
  the provisioned Tempo datasource exposes the reciprocal Loki mapping and
  Label-derived `trace_id` field.
- Resource sample during local acceptance: Loki 56.69 MiB RSS / 13.36% CPU,
  Loki MinIO 236.2 MiB RSS / 0.06% CPU, Collector 39.25 MiB RSS / 0.08% CPU.
  This is demo-host evidence, not production sizing.

## Completion gates

```text
uv run --locked ruff check .                         PASS
uv run --locked black --check .                     PASS
uv run --locked mypy                                PASS
uv run --locked pytest                              532 passed, 1 skipped
uv run --locked pytest tests --cov=iceberg ...      532 passed, 1 skipped; 92.72%
openspec validate --all --strict                    PASS
backlog validator                                   PASS (14 items)
git diff --check                                    PASS
```

Remote capability CI: run `33872665149` **SUCCESS** on exact implementation SHA
`095f057d143628b4b397a38386584441cc61b338`. It executed pinned-image/config
validation, clean Loki/Tempo/Collector startup, Grafana datasource provisioning,
static contracts, persisted acceptance and Loki/object-store outage recovery.
The first automatic run `33872446511` failed only because its Grafana API probe
omitted authentication; that probe was corrected in `095f057` and the manual
run passed. Core H1 remains independent; exact baseline H1 receipt is
`33869184341` SUCCESS on `07b475f`.

Final remote capability CI: run `33874499624` **SUCCESS** on exact
implementation SHA `fe51bdbda50bd7591e818e670479dc3c2ca0a793`. It reran the
same pinned-image, native OTLP, persisted redaction, Grafana correlation,
storage-isolation and outage/recovery contracts after the explicit label
allow-list correction.

Retention is configuration-verified (`retention_enabled=true`, 48h,
Compactor intervals and delete-request store); a literal 48-hour elapsed
expiry was not observed in this bounded run.

Exact implementation-SHA core H1: run `33874679399` **SUCCESS** on
`fe51bdbda50bd7591e818e670479dc3c2ca0a793`. Both the fresh-volume full
verification and NG-0.4 OTel-owned clean phases passed, including deterministic
E2E, dbt semantic contract, Prometheus/Grafana smoke, Collector outage parity,
and teardown. H1 ran without the Loki profile, proving profile independence.
The earlier exact-runtime receipt `33872953865` on `55acd9e` is retained as
historical evidence; the final exact-SHA run supersedes it for closure.

## Milestone 2B closure-blocker receipt

Local live acceptance on the M2B working tree passed the complete bounded
matrix. The pre-fix probe executed the redaction helpers from runtime SHA
`fe51bdb` and recorded the expected failure for `customer_email` and the full
payload marker; the repaired helper rejected bearer, password, API key,
connection string, PII, payload and sensitive SQL while retaining the event
name, severity, load ID and trace ID.

The live Grafana surface returned both Loki and Tempo datasource records and
same-trace proxy results. Storage checks allowed only the Loki bucket and
denied both canonical MinIO and the Tempo bucket with the same Loki identity.
Healthy and outage canonical probes returned the identical hash
`4ae600e920499c39b58c51282d0df41c8d72608c7c2e40ce02cee3a2af055c12`.

During Loki outage the first-party writer still emitted stdout and the
Collector reported a bounded log queue (capacity 256, observed size 2); after
restore a new log was queryable. Loki object-store outage left the canonical
hash unchanged and accepted new logs after storage recovery. Collector stop,
restart and post-restart ingestion also passed. The measured indexed labels
were `deployment_environment_name`, `service_name` and `service_namespace`,
each cardinality 1; the single query latency sample was 31ms (not a p95
statistic) and the Loki object-store measurement was 140 bytes for the bounded
fixture. Resource
sample: Loki 62.8MiB, Loki MinIO 229.5MiB, Collector 78.2MiB.

The adopted structured emitters are the writer, medallion and observability
exporter. Kafka, Spark and Airflow surfaces remain explicitly out of scope for
this first wave as documented in `design.md`; their framework/image contracts
were not changed.

## Exact M2B remote receipts

Capability CI run `33878459285` completed **SUCCESS** on exact implementation
SHA `ff7e6313869e70284bfe951f8a616d344298f1b7`. Its machine-checked acceptance
log included the pre-fix redaction failure demonstration, Grafana Loki/Tempo
proxy queries, both storage DENY checks, canonical healthy/outage hash parity,
Loki and object-store recovery, Collector restart, queue/WAL and resource
receipts.

Core H1 run `33878504266` completed **SUCCESS** on the same exact SHA. Both the
fresh-volume full verification and the NG-0.4 OTel-owned clean phases passed;
H1 remained Loki-disabled, so the canonical workload does not depend on the
optional Loki profile.

These receipts close the M2B acceptance blockers but do not authorise archive,
adoption or lifecycle transition. NG-0.6 remains `ACTIVE / pending`.

## Milestone 2C receipt

After binding `otlphttp/loki.sending_queue.storage` to the existing
`file_storage` extension, Collector v0.157.0 configuration validation passed.
The live M2C harness measured Collector WAL storage growth from 36,864 bytes to
528,384 bytes while Loki was unavailable, then hard-killed and restarted the
Collector before restoring Loki. The outage trace was queryable after restore,
proving persistent queue recovery. A deterministic 40,000-record burst while
Loki was down observed queue capacity 256 and queue size 176 (bounded; no
overflow counter was required because the near-capacity condition was met),
while canonical work remained successful. The latency receipt is explicitly a
single sample (`logql_latency_sample_ms`), not p95.

Exact M2C remote receipts: capability CI run `33884396179` completed
**SUCCESS** on implementation SHA `3a07da170fb460f5fd2342e63b29786529da013f7`.
It validated the Collector v0.157.0 configuration, persistent Loki queue,
near-capacity bounded pressure, hard-restart recovery and all prior M2B
contracts. Core H1 run `33884414502` also completed **SUCCESS** on the same
SHA with Loki disabled. The new runtime/config receipts supersede the earlier
M2B exact-SHA receipts for closure; lifecycle remains `ACTIVE / pending` until
separately authorised adoption/archive.

## Failed closure attempt and lifecycle-safe test repair

The first post-archive closure attempt at `2e1005b5ca50db1d7695063307a8710a1fc9453d`
was correctly reverted as `1013876d9c891bc2b40687b36a99cf22f437551b`. Capability
run `33888257726` and Core CI run `33888257735` exposed one test-contract defect:
`tests/test_loki_contract.py` read the temporary active-change path after the
archive had intentionally removed it, producing `FileNotFoundError`. The Loki
runtime and focused contracts were otherwise green. The repair makes the test
prefer the standing spec after adoption and fall back to the active design
before adoption, with focused coverage for both lifecycle states. No runtime,
Compose, Collector, Grafana, workflow, dependency, or logging-scope changes
are made by this repair.

## Final adoption and archive reconciliation

Implementation SHA: `3a07da170fb460f5fd2342e63b29786529da013f`.
Test-contract repair SHA: `de68270ad3bb5c993af5e35479115cf8aae1d733`.
Repair capability run `33889981082` completed **SUCCESS** on that exact repair
SHA. Repair Core CI run `33890376252` completed **SUCCESS** from source head
`de68270ad3bb5c993af5e35479115cf8aae1d733` using GitHub PR merge SHA
`a58f74df777cbee878e4670001b594ab2af3add9`; all four jobs were green.

The standing contract is `openspec/specs/loki-log-backend/spec.md`, and this
change is archived at
`openspec/changes/archive/2026-09-04-add-loki-log-backend/`. NG-0.6 is now
`DONE / ADOPTED`; NG-0.7 remains `PLANNED / pending` with authorization
`none`. The original M1 provenance and subsequent explicit M2, M2B, M2C,
test-repair and final adoption authorizations are retained in the backlog
history; no grant IDs are inferred.
