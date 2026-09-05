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

## Failed closure attempts and the lifecycle-safe test repair

Closure was attempted twice on `feature/ng-0.6-loki` and reverted both times.

The first attempt, `2e1005b`, was reverted as `1013876`. It failed for a real
reason: capability run `33888257726` and Core CI run `33888257735`, both
`pull_request` events on head `2e1005b`, base
`test/dbt-extensive-testing@9d62da49` via closed PR #5, ended in **failure**.
`tests/test_loki_contract.py` read
`openspec/changes/add-loki-log-backend/design.md` — a path the archive move
intentionally removes — producing `FileNotFoundError`. The Loki runtime and the
focused contracts were otherwise green, so the defect was in the test's
lifecycle assumption, not in the capability.

The repair, carried into this change from `de68270`, makes the test resolve the
scope contract by lifecycle: the standing specification once adoption has
happened, the active change design before it. Both states have focused
coverage. It changes no runtime, Compose, Collector, Grafana, workflow,
dependency or logging-scope behaviour.

The second attempt, `7d70f28`, was reverted as `f2bfb92`. A third, `9eb4356`,
was made on the same branch and merged into `test/dbt-extensive-testing` rather
than `main`.

## Why this closure was re-derived rather than merged

The three previous attempts and their receipts stayed on
`test/dbt-extensive-testing`, which diverged from `main`: at the point this
change was opened `main` was 7 commits ahead and 11 behind, with neither an
ancestor of the other. That line carries the Loki closure but not the adopted
`development-workflow` capability; merging it into `main` would have removed
the capability, its archived change, its fitness functions and the workflow
conversions — 1,887 deletions.

The receipts produced on that line are therefore recorded as history and are
**not** cited as adoption evidence:

| Run | Event | Head | Why not adoption evidence |
| --- | --- | --- | --- |
| `33902240453` H1 | `workflow_dispatch` | `9eb4356` | exact-SHA receipt for a commit not on `main`, whose tree lacks the adopted capability |
| `33903489346` Loki capability | `workflow_dispatch` | `9eb4356` | same |
| `33903909875` M5 gates | `workflow_dispatch` | `9eb4356` | same |
| `33904147775` Core CI | `pull_request` | `9eb4356` | base `test/dbt-extensive-testing@9d62da49` via closed PR #9, merge SHA `912dc9f` — not the integration target |
| `33908268598` H1 | `workflow_dispatch` | `d031679` | legacy line, pre-conformance gate definitions |

This is the requirement the `development-workflow` capability states: a receipt
cited as evidence that a change is ready to integrate must have been produced
against the branch the change actually integrates into. Every run above is
genuine and green; none of them answers that question.

Only `de68270`'s test repair was carried. The two closure attempts, their two
reverts, the redundant `71b1bc3` documentation commit with its revert
`a3eea07`, and the two merge commits `7f8a814` and `d031679` were dropped. The
`71b1bc3` sentence was checked rather than assumed redundant: every token the
repaired test asserts — `Kafka producer`, `Spark streaming jobs`,
`Airflow DAG code`, `first adopted wave` — is already present in the standing
specification candidate through other wording.

The 117-line standing-spec candidate from `9eb4356` was reconciled against the
active 103-line delta and current `main`. Requirement count and semantics were
preserved; four requirement titles contain editorial reconciliation only —
`First-party structured records` → `…and bounded scope`, `Native OTLP route` →
`Native OTLP ingestion`, `Fail-open observability` → `Fail-open persistent
buffering`, `Capability evidence` → `…and profile independence`. Nothing in it
was adopted on `main` before this change; until the protected merge lands it is
a proposed integration state, not a standing capability.

## Final closure receipts

Receipts are separated by what they can answer. Conflating the three classes is
how the earlier closure came to cite a green run that proved nothing about the
integration it was offered for.

### Class 1 — historical evidence, explicitly not adoption evidence

The five runs produced on `feature/ng-0.6-loki` and `test/dbt-extensive-testing`,
tabulated above (`33902240453`, `33903489346`, `33903909875`, `33904147775`,
`33908268598`), plus the two diagnostic failures `33888257726` and
`33888257735` that exposed the test-lifecycle defect. All are genuine. None was
produced against `main`, and none is cited here as a reason to adopt.

### Class 2 — capability evidence on the adoption candidate

Candidate **X = `51ca4acdb1e174ad17097fe6c7fd14bbec5a686d`**, branched from
`main` at `acbce84a1eeb2c98b628b44172c9bb12dcd98209`.

| Gate | Invocation | Run | Jobs | Result |
| --- | --- | --- | --- | --- |
| NG-0.6 Loki capability | `workflow_call` via `ci-capability-dispatch`, `expected_sha` = X | `33912934372` | preflight `101153390074`; capability `101153426177` | **success** |
| H1 clean reproducible stack (Loki-free core) | `workflow_dispatch`, exact SHA | `33912936640` | `101153399517` fresh volumes; `101153399069` NG-0.4 OTel phases | **success** |
| M5 architecture gates | `workflow_dispatch`, exact SHA | `33912940204` | `101153410957` | **success** |

Every run's `head_sha` is X. The capability gate was reached through
composition: the dispatcher's preflight asserted operator intent equalled the
resolved ref before the callee started, and the callee's own
`Verify exact implementation SHA` step compares its checkout `HEAD` against
`GITHUB_SHA`. `NG-0.5 Tempo capability (called)` was `skipped`, as the selected
capability was `ng06-loki`.

H1 was dispatched explicitly rather than left to the pull request: nothing this
change touches matches `ci-h1-clean.yml`'s path filter, so it would not have
fired, and the change's own `Capability evidence` requirement obliges a
Loki-free core H1. Reducing acceptance to whatever the pull request happens to
trigger would have silently dropped it.

### Class 3 — merge-time authority

Pull request **#14**, `Adopt NG-0.6 Loki capability, re-derived from main`.

| | |
| --- | --- |
| Head | `feat/ng-0.6-adoption` @ **Y** = `d8ab3115e859ea4f373b83a2b1c3aea3fe9d8fa9` |
| Base | base `main@acbce84a` — `acbce84a1eeb2c98b628b44172c9bb12dcd98209` |
| Merge commit | `978863de8bfacba35678e28dc04bd7e216f7a6c7` |
| Merged | 2026-09-04T20:05:46Z, squash |
| Branch after merge | deleted automatically |

Workflow runs on Y, all `pull_request`, all **success**, base
`main@acbce84a`:

| Workflow | Run | Conclusion |
| --- | --- | --- |
| CI | `33914145058` | success |
| M5 architecture gates | `33914145097` | success |
| NG-0.6 Loki capability | `33914145320` | success |

Required check jobs on Y: Lint + compose validation `101157291884`, Unit tests
+ coverage `101157291827`, Warehouse dbt contract + artifacts `101157291773`,
Airflow DAG validation `101157291535`, PR M3/M4 recovery and cutover gates
`101157290906`, capability `101157291888`.

Commit Y changes only evidence prose relative to X, so the Class 2 gates were
not re-run on it. X remains the verified capability candidate, and Y takes its
authority from the required checks on the final pull request head. That is
where the recursion of "recording a receipt moves the head" terminates.

This is the receipt the whole `development-workflow` capability was written to
require: a green run whose base is the branch the change actually integrates
into, recorded by branch **and** SHA so a reader can tell what was merged
without reconstructing the pull request. Contrast the Class 1 table above,
where every run is equally green and none of them answers that question.

NG-0.6's lifecycle is `DONE / ADOPTED` in the backlog register as of
2026-09-04; the `ACTIVE / pending` statements earlier in this file describe the
state at the time each section was written and are not the current state.
