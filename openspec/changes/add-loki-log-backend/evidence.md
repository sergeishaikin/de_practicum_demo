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
expiry was not observed in this bounded run. Canonical parity was checked by
keeping canonical MinIO and the Collector healthy during Loki stop/restart;
the full business workload parity remains a follow-up acceptance detail, not
an adoption claim.

Exact implementation-SHA core H1: run `33874679399` **SUCCESS** on
`fe51bdbda50bd7591e818e670479dc3c2ca0a793`. Both the fresh-volume full
verification and NG-0.4 OTel-owned clean phases passed, including deterministic
E2E, dbt semantic contract, Prometheus/Grafana smoke, Collector outage parity,
and teardown. H1 ran without the Loki profile, proving profile independence.
The earlier exact-runtime receipt `33872953865` on `55acd9e` is retained as
historical evidence; the final exact-SHA run supersedes it for closure.
