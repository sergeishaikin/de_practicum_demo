# H1 — reproducible runtime and deployment hardening

Status: VERIFIED locally on a fresh-volume stack; the repeatable CI gate is
defined by `.github/workflows/ci-h1-clean.yml`.

## Contract

A clean machine receives the repository plus declared deploy-time secrets and
can reproduce the verified stack without runtime Maven/Ivy/Python dependency
resolution, mutable image tags, startup package installation, or assumptions
about old Docker volumes.

H1 does not change Bronze/Silver/Gold semantics, B2, durable progress/recovery,
dbt semantic contracts, D-3a, multi-writer ownership, or observability logic.

## Immutable runtime inventory

The committed `.env.example` records immutable manifest digests for external
Compose images. Custom images pin their base images in their Dockerfiles:

| Runtime | Pin | Dependency source |
|---|---|---|
| Spark | `4.2.0-java21-python3` + digest | `spark/Dockerfile` |
| PyIceberg writer/medallion | Python 3.12 slim + digest | `iceberg/requirements.txt` |
| Observability exporter | Python 3.12 slim + digest | `observability/requirements.txt` |
| Producer | Python 3.12 slim + digest | `kafka/producer/requirements.txt` |
| Airflow | 3.3.1 / Python 3.12 + digest | `airflow.requirements.txt` |
| dbt | dbt-core 1.12.0, dbt-trino 1.10.3 | `dbt/requirements.txt` |

Python dependency inputs live in `pyproject.toml` (host development) and the
service-specific `requirements.in` files. `uv.lock` locks the host environment;
the generated `requirements.txt` files lock every service transitively and
include artifact hashes. All custom Python images copy `uv` 0.12.5 from a
digest-pinned image and install with `--require-hashes`. The host and Iceberg
inputs share the PyArrow/PyIceberg pins. CI uses `uv sync --locked` and surfaces
runtime versions in the clean-stack evidence artifact.

`airflow.constraints.txt` is the relevant subset of Airflow 3.3.1's official
Python 3.12 constraints. It keeps the locked Trino client dependencies aligned
with the environment already fixed by the Airflow base-image digest. Trino
0.338.0 matches the official Airflow 3.3.1 constraint.

Regenerate every Python lock after changing an input:

```powershell
.\scripts\lock-python-dependencies.ps1
```

On macOS/Linux use `./scripts/lock-python-dependencies.sh`.

## Spark dependencies are baked

`spark/h1-runtime-jars.lock` is the complete pinned coordinate set resolved at
image build time for dependencies not already shipped by the pinned Spark base
image. The Dockerfile downloads those artifacts while building the image and
verifies availability by failing the build if any artifact is missing.
`lz4-java:1.11.0` is explicitly supplied by that pinned base image. 
`/usr/local/bin/spark-submit-h1` supplies the baked JAR set with `--jars`.

The Compose streaming job and deterministic E2E use that wrapper. There is no
runtime `--packages`, Maven Central lookup, or Ivy cache volume. Build-time
network access is expected; container startup does not depend on it.

## Configuration and secrets

`scripts/validate_runtime_config.py` checks required variables, valid ports,
immutable image digests, and rejects placeholder secrets in the clean profile.
`.env.example` is a deploy-time template, not a credential store. The clean
workflow creates short-lived CI-only secrets in its workspace. Local demo
values must be supplied through an ignored `.env` file. An existing pre-H1
`.env` must be refreshed with the new image pins and required secret keys
before running `scripts/stack-up.ps1`; the launcher intentionally rejects an
incomplete configuration before starting Compose.

Airflow and Superset do not contain hardcoded runtime secret values in
Compose. Airflow receives distinct API and JWT secrets from `.env`; its
loopback-only local UI uses Simple Auth Manager all-admin mode without a login.

## Bootstrap and readiness

`scripts/bootstrap_stack.py` is idempotent. It polls Iceberg REST, Trino,
Kafka, Prometheus, and Grafana readiness; creates the MinIO bucket with
`--ignore-existing`; and creates catalog schemas with `IF NOT EXISTS`.
`scripts/stack-up.ps1` creates the external network before Compose and invokes
configuration validation plus bootstrap.

The clean workflow destroys volumes before startup, builds the images, runs
bootstrap, waits for canonical Bronze, then executes integration, E2E, dbt,
and observability gates. It destroys the clean stack afterward.

## OTel acceptance evidence

The `otel-acceptance` job runs the deterministic E2E three times on one commit —
Collector disabled (`off`), enabled (`on`), and enabled but stopped mid-run
(`outage`) — and each phase starts from destroyed volumes. It asserts two
independent properties, and the distinction matters:

| Property | Question | Evidence |
|---|---|---|
| Correctness | did each phase produce the right result? | `observed_contract == expected_contract`, per phase |
| Transparency | did telemetry change the result? | `observed_*_sha256` identical across `off`/`on`/`outage` |

**The observed contract is read from the running stack, never re-derived from
the fixture.** `tests/e2e/test_lakehouse_e2e.py` queries live Kafka offsets,
the landing prefix, Trino, and `marts.lakehouse_metrics` immediately before its
`finally` block drops the namespace, the landing prefix and the topic, and
writes the result to the path in `E2E_OBSERVED_EVIDENCE_PATH`. There is no
window in which an out-of-process observer could take that measurement: once
pytest returns, the isolated state is gone.

Alongside the aggregate contract the test records `observed_gold_snapshot` — every
materialised `orders_daily_metrics` row as Trino rendered it, ordered and
canonically formatted — and hashes it. Row counts and summed revenue are
satisfied by many different tables; the rows are what cross-phase equality has
to mean.

Every SQL NULL in that snapshot has exactly one spelling, `<null>`, and each
column is rendered by testing for NULL *before* formatting. The obvious
`coalesce(format('%.6f', x), '<null>')` is wrong and silently so: Trino's
`format` follows Java's Formatter and renders a NULL argument as the string
`"null"`, so the coalesce never fires. That shipped once — the first hardened
run recorded a numeric NULL as `"null"` in the same row where a NULL country had
correctly become `"<null>"` — and the validator now rejects any non-canonical
spelling, so the next regression fails the gate instead of waiting to be noticed
in an artifact nobody opens.

An earlier version of this job computed its parity digest from
`expected_pipeline(build_fixture())`, a pure function of the checked-out test
source. All three digests were therefore identical by construction, the
mismatch branch was unreachable, and `canonical_parity: PASS` was printed on
every run that reached it. `tests/test_otel_acceptance_evidence.py` now pins
that the workflow neither re-derives the contract nor prints a verdict itself.

Three rules hold for everything in this bundle:

- **An absent measurement is never a value.** A missing OTel WAL volume, a
  failed `du`, or non-numeric output fails the phase; it does not record `0`.
  `set -euo pipefail` is load-bearing — `pipefail` is what surfaces a failing
  `docker run` through the pipe into the guard.
- **`docker stats` output is parsed before it is believed.**
  `scripts/capture_container_resources.py` records each container's expected and
  observed state and refuses to store a stats object it could not parse, so
  `stats: null` means "declared stopped and confirmed stopped", never "not
  measured". The declaration is itself checked: only the `outage` phase may
  declare the Collector stopped.
- **`|| true` is confined to teardown and best-effort diagnostics.** It is
  forbidden in setup, assertions, acceptance measurements, and evidence
  generation, and a test enforces this for the acceptance step.

`scripts/validate_otel_acceptance.py` is the only thing that prints `PASS`. It
recomputes every digest from the payload that carries it, so a receipt cannot
claim a hash its own contents do not produce, and rejects the bundle when a
phase is missing, when the phases disagree, when they did not run on one commit,
or when they are three copies of a single run. `Assert the acceptance bundle is
complete` then names every per-phase artifact explicitly — a wildcard upload
path matches two files as happily as three — and the upload uses
`if-no-files-found: error`.

The clean-stack H1 workflow may still use a SQLite-backed demo REST catalog,
so its metadata commits are intentionally serialized during that isolated
verification. The persistent rollout catalog is now PostgreSQL-backed: the
SQLite catalog was preserved with SHA-256 evidence, its registrations were
imported without rewriting Iceberg data/metadata files or advancing snapshots,
and before/after table inventories proved exact metadata-pointer, UUID,
snapshot, schema, partition, and sort-order equality. The live PostgreSQL
catalog was then exercised with overlapping writer, medallion, Trino, and dbt
clients without SQLite locking or `UncheckedSQLException` failures. See
`artifacts/b2-rollout/02a-catalog-equivalence.json` and
`02a-catalog-recovery.json` for the migration receipt. This change does not
alter Bronze, Silver, Gold, or dbt model semantics.

## Upgrade and rollback expectations

To upgrade a runtime, change the digest or pinned dependency deliberately,
rebuild the affected image with `--pull --no-cache`, run the clean workflow,
and review its version evidence. Rollback means reverting the pin to the
previous verified commit/digest and rebuilding; persistent data volumes are
not silently migrated by image startup.

## Verification commands

```powershell
uv run --locked python scripts/validate_runtime_config.py --env-file .env --profile local
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config
uv run --locked python scripts/bootstrap_stack.py --env-file .env
```

The authoritative clean-machine gate is the H1 GitHub Actions workflow, not a
warm local stack.

## Verification evidence

The implementation checkpoint was verified locally without changing the
existing persistent demo volumes:

- `docker compose ... build --pull` completed for all custom services;
- `de-practicum-demo-spark:4.2.0-h1` contains 16 baked runtime JARs and
  `spark-submit-h1 --version` reports Spark 4.2.0 on Java 21;
- Compose configuration validation completed with `.env.example`;
- H1 tests: `9 passed`;
- fast suite: `126 passed, 30 deselected`, using a workspace-local pytest
  temporary directory;
- Ruff and `git diff --check` passed.

Additional live warm-stack evidence after the H1 image recreation:

- integration: 18 passed, 1 expected failure;
- deterministic E2E: 3 passed after catalog-writer quiescence;
- dbt semantic models: 2/2 created with serialized commits;
- dbt data tests: `PASS=26 WARN=0 ERROR=0 TOTAL=26`;
- Prometheus readiness and Grafana health: HTTP 200, with a healthy
  Prometheus target.

Fresh-state evidence was executed locally on 2026-08-09 without deleting the
verified persistent demo volumes. The running services were stopped, their
ephemeral containers and network were recreated, and a temporary Compose
overlay isolated all stateful data in `h1_clean_*` volumes. The pinned stack
was built with `--pull always` and passed:

- fresh network, volumes, MinIO bucket, catalog schemas, and readiness;
- integration: `18 passed, 1 xfailed`;
- deterministic E2E: `3 passed`;
- dbt parse/compile, 2 semantic views, and `PASS=26 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=26`;
- Prometheus readiness HTTP 200, Grafana health HTTP 200/database ok, and a healthy Prometheus target;
- Spark 4.2.0 / Scala 2.13.18 / Java 21.0.11 and Trino CLI 483 runtime evidence.

Only the temporary `h1_clean_*` volumes were removed afterward. The original
persistent volumes were preserved and the demo stack was restored and passed
the idempotent bootstrap/readiness check. The GitHub Actions workflow remains
the authoritative clean-machine gate and records logs, dbt artifacts, image
and version evidence, and final teardown.
