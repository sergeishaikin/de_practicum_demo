# H1 — reproducible runtime and deployment hardening

Status: VERIFIED locally on a fresh-volume stack; the repeatable CI gate is
defined by `.github/workflows/ci-h1-clean.yml`.

## Contract

A clean machine receives the repository plus declared deploy-time secrets and
can reproduce the verified stack without runtime Maven/Ivy resolution,
mutable image tags, startup `pip install`, or assumptions about old Docker
volumes.

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
| Airflow | 2.9.3 / Python 3.12 + digest | `airflow.Dockerfile` |
| dbt | dbt-core 1.12.0, dbt-trino 1.10.3 | `dbt/requirements.txt` |

The host `requirements-dev.txt` uses the same PyArrow/PyIceberg pins as the
Iceberg runtime. CI installs the declared files and surfaces runtime versions
in the clean-stack evidence artifact.

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

Airflow and Superset no longer contain hardcoded runtime secret values in
Compose. The Airflow admin password is injected through configuration.

## Bootstrap and readiness

`scripts/bootstrap_stack.py` is idempotent. It polls Iceberg REST, Trino,
Kafka, Prometheus, and Grafana readiness; creates the MinIO bucket with
`--ignore-existing`; and creates catalog schemas with `IF NOT EXISTS`.
`scripts/stack-up.ps1` creates the external network before Compose and invokes
configuration validation plus bootstrap.

The clean workflow destroys volumes before startup, builds the images, runs
bootstrap, waits for canonical Bronze, then executes integration, E2E, dbt,
and observability gates. It destroys the clean stack afterward.

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
python scripts/validate_runtime_config.py --env-file .env --profile local
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config
python scripts/bootstrap_stack.py --env-file .env
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
