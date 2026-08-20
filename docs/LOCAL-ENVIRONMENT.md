# Local environment

This repository has a real local runtime. It is not a fallback for when CI is
unavailable, and CI is not a substitute for it.

The document has two halves, and the split is the point. The **execution
contract** is normative and stays true until someone deliberately changes it.
The **measured snapshot** is evidence with a date on it, and it goes stale.
Anything written in the wrong half becomes a lie: a contract that hardcodes
"15.49 GB of Docker memory" is wrong the moment the setting changes, and a
snapshot that says "the agent SHALL start Docker" is not a measurement.

Volatile facts are not maintained by hand at all. Run:

```bash
uv run python scripts/local_runtime_inventory.py
```

## A. Execution contract

Normative. `SHALL` and `SHALL NOT` are intentional.

- The primary development host is **Windows**, with Docker Desktop installed.
- Docker Desktop is an **available local runtime**.
- Docker Desktop **may be stopped** between development sessions.
- **A stopped Docker daemon is not an unavailable dependency.** It is a
  startable state. The distinction is the entire reason this document exists.
- When authorised work requires live services, the agent **SHALL** start Docker
  Desktop, wait for the engine to become ready, and run the required services.
- Local live verification **SHALL** be performed whenever the required stack can
  run on this machine.
- GitHub Actions clean-stack CI is **independent reproducibility evidence**. It
  is not a replacement for an available local runtime, and "CI will run it" is
  not a reason to skip a local check that could have run.
- Only the services required by the current change **SHOULD** be started. The
  full graph is 22 services; almost no change needs all of them.
- Stateful and destructive operations remain governed by the repository safety
  contract in `AGENTS.md`. This document widens what may be *run*, not what may
  be *destroyed*.

### The decision rule

```text
Does the authorised change require live runtime evidence?
  no  -> host verification only (uv run pytest, ruff, black, mypy)
  yes
   |
   +-- Is Docker Desktop installed?
   |     no  -> a genuine environment limitation; record it and use CI
   |     yes
   |      |
   |      +-- Is the Docker engine responding?
   |            no  -> START DOCKER DESKTOP, wait for readiness
   |            yes -> continue
   |      |
   |      +-- Start the minimum services the change needs
   |      +-- Wait for readiness (healthchecks / config endpoints)
   |      +-- Run the local acceptance tests
   |      +-- Capture the evidence
   |      +-- Stop any temporary capability profile
   |      +-- Then run clean-stack CI as independent reproduction
```

**"Docker is stopped" is never a branch that leads to "skip the test."** If a
report says a live check could not run, it must name which of the boxes above
actually failed.

### Starting the engine

`docker --version` answers whether the CLI exists. It says nothing about the
engine, and conflating the two is how a stopped daemon gets misreported as an
absent one. The engine check is:

```bash
docker info --format '{{.ServerVersion}}'
```

If that fails, start Docker Desktop and poll until it succeeds:

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
for ($i = 0; $i -lt 60; $i++) {
    docker info --format '{{.ServerVersion}}' 2>$null
    if ($?) { break }
    Start-Sleep -Seconds 5
}
```

### Always pass both Compose files

The extended file declares `de_demo_net` as `external: true`; the base file
declares it normally. Starting only `docker-compose.yml` against a network that
already exists fails with a label mismatch:

```text
network de_demo_net was found but has incorrect label com.docker.compose.network
```

Use both `-f` flags, as `stack.ps1` and CI do, and pre-create the network:

```bash
docker network create de_demo_net || true
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml up -d <services>
```

### Image pins differ between local and CI

The committed `.env.example` pins every image **by digest**. A developer's local
`.env` may not, and on this machine it does not.

That is not a defect to fix silently — a local `.env` is uncommitted and belongs
to the developer — but it does mean **a local result and a CI result are not
automatically comparable**. `scripts/local_runtime_inventory.py` reports the
drift, and any performance or compatibility claim made locally must name the
image it actually ran against.

`tests/test_provenance_contract.py::test_committed_compose_pins_every_image`
guards the Compose files, where these images appear as `${VAR}` references. It
therefore cannot see this drift, and is not intended to.

## B. Measured snapshot

**Evidence, not a permanent architectural guarantee.** These values were true on
the date below, on one machine. Re-measure before relying on any of them for a
resource or performance decision; regenerate with
`scripts/local_runtime_inventory.py`.

```text
Captured at:              2026-08-20
Host:                     Windows 11 Pro 10.0.26200
CPU:                      11th Gen Intel Core i7-1185G7 @ 3.00GHz
Logical CPUs:             8
Host RAM:                 31.73 GB
Architecture:             AMD64

Docker Engine:            29.5.3
Docker Compose:           5.1.4
Docker backend:           WSL2 (kernel 6.18.33.1-microsoft-standard-WSL2)
Docker CPU allocation:    8
Docker memory allocation: 15.49 GB
Docker storage driver:    overlayfs at /var/lib/docker

Docker disk usage:        images 30.78 GB (4.53 GB reclaimable)
                          volumes 29.15 GB (25.04 GB reclaimable)
```

### Runtime graph

Derived from Compose, not transcribed:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config --services
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config --images
```

As measured: **22 services**, **16 distinct images**, of which **6 are built
locally**:

```text
de-practicum-demo-airflow:0.1.0
de-practicum-demo-iceberg:0.11.1-h1
de-practicum-demo-jupyter:spark420-h1
de-practicum-demo-observability:0.22.1-h1
de-practicum-demo-orders-producer:0.1.0
de-practicum-demo-spark:4.2.0-h1
```

### Measured profile cost

The minimum profile for Iceberg integration work, while healthy and idle:

| Service | Memory | CPU |
|---|---|---|
| `de-demo-minio` | 397 MiB | 0.05% |
| `de-demo-iceberg-rest` | 250 MiB | 0.29% |
| `de-demo-postgres` | 46 MiB | 0.04% |
| **total** | **~0.7 GB of 15.49 GB** | negligible |

Startup to readiness was under five seconds from an existing image cache, and
the live M5 gate suite ran in **31 seconds** against it.

This is the number that matters for the resource-sensitive NG items: the
baseline is small, so a capability profile's cost should be measured against
this floor rather than assumed from an ADR estimate. **Do not claim this host
cannot support a profile until the profile has been started and measured.**
