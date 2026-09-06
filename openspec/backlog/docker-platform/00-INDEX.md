# Docker Platform — Gap Programme

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This package records planned work only; it does not authorize implementation.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `main`
> **Baseline date:** 2026-09-06

## Purpose

This programme converts the Docker/container gap analysis into a bounded set of OpenSpec backlog items for the current local Data Engineering Platform.

The baseline is already strong: Docker Compose is the runtime model; external images are digest-pinned; Python dependencies use hashes; the stack uses a user-defined bridge network, named volumes, profiles, memory ceilings, meaningful health checks for several critical services, non-root users in several custom images, bounded json-file logging on part of the extended stack, Buildx in CI, live Compose integration tests, and optional Prometheus/Grafana/OTel/Tempo/Loki observability.

The programme therefore does **not** replace the working container architecture. It targets six residual gaps that are measurable and independently reviewable: readiness semantics, runtime-secret containment, least-privilege runtime hardening, bounded Docker-log coverage, image supply-chain assurance, and evidence-based BuildKit efficiency.

## Measured baseline

Measured against `main` on 2026-09-06:

- PostgreSQL, Kafka, Spark Connect and Iceberg REST have explicit health checks; PostgreSQL already demonstrates the desired standard by probing the same TCP path its dependants use.
- The inspected dependency graph contains **at least 9 `service_started` dependency edges** where a consumer may start before the upstream service is proven usable: Spark master→MinIO; Spark worker→Spark master; Spark Connect→Spark master/worker; Jupyter→Spark master/worker/MinIO; Iceberg REST→MinIO; Iceberg writer→MinIO. MinIO itself has no health check in the current extended Compose file.
- `.env.example` contains **at least 14 password/secret-style runtime values** (`POSTGRES_PASSWORD`, `AIRFLOW_DB_PASSWORD`, `MINIO_ROOT_PASSWORD`, Grafana/Superset/Airflow/Tempo/Loki/OpenMetadata credentials and related secrets). They are excluded from the image build context, but the runtime delivery mechanism is environment-variable based rather than Compose secret mounts.
- Airflow, Spark and Jupyter custom images explicitly return to non-root runtime users. `iceberg/Dockerfile` declares no `USER`, while `iceberg-rest` is explicitly configured as `user: "0:0"`.
- Airflow binds its UI to `127.0.0.1`, while multiple extended-stack ports use `${HOST_PORT}:container_port` and therefore do not express loopback-only exposure in Compose.
- `x-bounded-logging` limits `json-file` logs to `50m × 3` and is attached to several Spark/Iceberg services; it is not a repository-wide contract for every long-running container.
- Third-party images are pinned by digest and custom Python installs use `--require-hashes`. CI uses Buildx for at least the Airflow E2E image build. Repository search finds no Trivy-based image vulnerability gate and no standing SBOM/provenance requirement.
- The Spark Dockerfile already orders its large pinned JAR download layer before the frequently edited submit wrapper, explicitly protecting cache reuse. No programme claim is therefore that Docker build caching is absent; NG-4.6 measures whether additional BuildKit caching is actually worthwhile.

These figures are a planning baseline, not future authority. Every item SHALL remeasure the current repository when promoted.

## Backlog register

| Item | File | Gate | Depends on | Change | State | Disposition | Authorised by | At |
|---|---|---|---|---|---|---|---|---|
| NG-4.1 | `NG-4.1-container-readiness.md` | ADOPT | - | `harden-container-readiness` | PLANNED | pending | `none` | - |
| NG-4.2 | `NG-4.2-runtime-secret-containment.md` | ADOPT | - | `contain-runtime-secrets` | PLANNED | pending | `none` | - |
| NG-4.3 | `NG-4.3-runtime-least-privilege.md` | ADOPT | - | `harden-container-runtime-privileges` | PLANNED | pending | `none` | - |
| NG-4.4 | `NG-4.4-bounded-container-logging.md` | ADOPT | - | `bound-container-runtime-logs` | PLANNED | pending | `none` | - |
| NG-4.5 | `NG-4.5-image-supply-chain.md` | ADOPT | - | `add-container-supply-chain-assurance` | PLANNED | pending | `none` | - |
| NG-4.6 | `NG-4.6-buildkit-efficiency.md` | EXPERIMENT | - | `evaluate-buildkit-cache-efficiency` | PLANNED | pending | `none` | - |

The rows are intentionally mostly independent. A security or correctness fix must not be blocked on a build-performance experiment. Completing one item never authorises another.

## Why six changes rather than one `harden-docker`

Each item has a different failure mode, evidence shape and rollback boundary.

- **NG-4.1** is a startup correctness contract. It asks whether a dependency is *usable*, not merely running.
- **NG-4.2** changes how secret material reaches processes and therefore needs service-by-service compatibility and leak evidence.
- **NG-4.3** changes Unix identity, host exposure and kernel privilege boundaries; its rollback is per service and must not be coupled to secret migration.
- **NG-4.4** is operational disk-safety policy. Logging-driver changes can be accepted without changing process privileges or credentials.
- **NG-4.5** is CI/software-supply-chain policy over immutable images and dependencies.
- **NG-4.6** is an experiment. It is adopted only if measurements prove a useful build-time improvement without weakening reproducibility.

Combining them would make one PR require unrelated live failure tests, security migration, CI policy and build benchmarks before any one benefit could land.

## Explicit non-goals

- No Kubernetes, Docker Swarm, Helm, service mesh, autoscaling or production HA.
- No multi-broker Kafka, HA PostgreSQL or cluster scheduler redesign.
- No migration away from Docker Compose as the local platform runtime.
- No blanket Alpine/distroless conversion.
- No remote image registry solely to satisfy this programme.
- No multi-architecture requirement unless a separately authorised platform requirement introduces one.
- No claim that every container must be `read_only`, capability-free or non-root; documented incompatibilities and stateful write paths are valid exceptions when proven.
- No secret-management product such as Vault merely for feature breadth; use the smallest mechanism that improves the current local contract.

## Cross-cutting invariants

1. **The data platform remains reproducible.** Digest pinning, dependency hashing and lockfiles SHALL NOT be weakened.
2. **Core data semantics are unchanged.** Docker hardening SHALL NOT alter Iceberg snapshots, Kafka recovery, Airflow/dbt behavior, medallion semantics or canonical outputs.
3. **Optional planes remain optional.** A hardening change SHALL NOT make observability, BI or metadata profiles correctness dependencies of the core stack.
4. **Health means usable by the dependant path.** A probe that merely proves a PID or open socket when the consumer needs a stronger condition does not satisfy NG-4.1.
5. **Secret material never becomes evidence.** Acceptance receipts SHALL identify secret names/sources, never values.
6. **Security changes fail visibly.** An incompatibility is recorded as an exception or hard stop; the change SHALL NOT silently fall back to a broader privilege/credential model and claim success.
7. **Developer usability is measured, not assumed.** Hardening and BuildKit changes SHALL keep the documented Windows/WSL2 local workflow usable within the existing resource envelope.
8. **The programme does not authorise itself to grow.** Anything outside NG-4.1 … NG-4.6 requires a separate operator grant.

## Promotion contract

For each item:

1. obtain explicit operator authorisation unless a separately recorded bounded programme authorisation covers it;
2. open exactly the change id named in the register;
3. re-read current `main`, standing specs, Compose files, Dockerfiles, CI and relevant tests;
4. remeasure the baseline before designing the implementation;
5. revalidate time-sensitive Docker/tool capabilities from primary documentation where applicable;
6. create `proposal.md`, `design.md`, `tasks.md`, the required spec delta, and an `evidence.md` plan before implementation;
7. prove non-vacuity by showing the new detector/gate catches at least one real or synthetic pre-change violation;
8. run the repository completion gate plus the item's live acceptance evidence;
9. archive/adopt only after integration evidence exists;
10. stop unless the next item is separately authorised.

## Freshness of external assumptions

Docker Compose, BuildKit/Buildx, image-scanning tools, SBOM formats and upstream container-image behavior change over time. Product/tool behavior captured on 2026-09-06 SHALL be reverified from primary documentation at promotion. Repository-local facts SHALL be remeasured from current `main` rather than copied from this baseline.