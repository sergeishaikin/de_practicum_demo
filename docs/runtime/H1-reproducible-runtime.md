# H1 — reproducible runtime and deployment hardening

Status: implementation complete; clean-state verification is defined by
`.github/workflows/ci-h1-clean.yml`.

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

The demo REST catalog is SQLite-backed, so metadata commits are intentionally
serialized during verification: the workflow quiesces the always-on Iceberg
writer and medallion before deterministic E2E, and dbt semantic models run
with one thread. This is deployment/test orchestration for the demo catalog;
it does not change Bronze, Silver, Gold, or dbt model semantics.

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
- H1 tests: 8 passed;
- fast suite: 125 passed, 30 deselected, using a workspace-local pytest
  temporary directory;
- Ruff and `git diff --check` passed.

Additional live warm-stack evidence after the H1 image recreation:

- integration: 18 passed, 1 expected failure;
- deterministic E2E: 3 passed after catalog-writer quiescence;
- dbt semantic models: 2/2 created with serialized commits;
- dbt data tests: `PASS=26 WARN=0 ERROR=0 TOTAL=26`;
- Prometheus readiness and Grafana health: HTTP 200, with a healthy
  Prometheus target.

The clean-volume workflow was not run against the local persistent demo stack,
because its required `down --volumes` step would delete the verified S1.1
historical migration state. The workflow is the remaining clean-machine gate
and records logs, dbt artifacts, image/version evidence, and final teardown.
An isolated Docker-in-Docker attempt did build the pinned images and create
fresh volumes/network, but the nested daemon became unresponsive during
bootstrap under local resource pressure; it is not counted as a clean pass.
