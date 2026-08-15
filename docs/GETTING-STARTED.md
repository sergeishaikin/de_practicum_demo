<!-- generated-by: gsd-doc-writer -->
# Getting Started

## Prerequisites

- Windows 10 or Windows 11 with Docker Desktop (Linux containers) and the WSL2 backend, or macOS/Linux with Docker. See [quickstart_windows.md](quickstart_windows.md) or [quickstart_macos_linux.md](quickstart_macos_linux.md) for platform-specific setup.
- PowerShell 5.1 or 7 (Windows) or a POSIX shell (macOS/Linux).
- Git to clone the repository.
- `uv` 0.12.5 for the host-side validation and bootstrap commands.
- At least 12 GB of RAM available to Docker; 16 GB is preferable.
- Docker with Docker Compose v2 (`docker compose version` should succeed).

The full extended stack runs 18 containers. The base stack (PostgreSQL + Airflow) needs only two.

## Installation steps

```bash
git clone https://github.com/dim4eg91/de_practicum_demo.git
cd de_practicum_demo
uv sync --locked
```

Create the runtime environment file (the `.env.example` values are safe defaults):

```powershell
Copy-Item .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

Add `SUPERSET_SECRET_KEY` to `.env` before starting the extended stack if you use Superset — it is required by the `superset` and `superset-mcp` services and has no default (see [CONFIGURATION.md](CONFIGURATION.md)).

Validate the Compose files:

```powershell
docker compose --env-file .\.env -f .\docker-compose.yml -f .\docker-compose.extended.yml config
```

Build and start:

```powershell
.\stack.ps1 build
.\stack.ps1 up
.\stack.ps1 status
```

On macOS/Linux use `docker compose` directly, e.g.:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml up -d
```

## First run

After `stack.ps1 up` finishes, the platform is ready when `stack.ps1 status` shows the containers as running/healthy.

Open the main UIs:

| Component | URL |
|---|---|
| Airflow | `http://localhost:18085` (login `admin` / `admin`) |
| Jupyter | `http://localhost:18888` |
| MinIO console | `http://localhost:19001` |
| Trino | `http://localhost:18082` |
| Kafka UI | `http://localhost:18090` |
| Spark Master UI | `http://localhost:18080` |
| Metabase | `http://localhost:13000` |
| Superset | `http://localhost:18088` |

Verify the end-to-end pipeline once data has flowed (a minute or two after startup):

```bash
docker exec de-demo-trino trino --execute "SELECT count(*) FROM iceberg.bronze.orders"
docker exec de-demo-trino trino --execute "SELECT count(*) FROM iceberg.silver.orders_clean"
docker exec de-demo-trino trino --execute "SELECT event_date, country, status, orders_count, total_amount FROM iceberg.gold.orders_daily_metrics LIMIT 10"
```

The counts grow over time because `orders-producer` publishes continuously. For the batch pipeline, enable and trigger the `demo_core_marts_pipeline` DAG in Airflow.

## Common setup issues

- **PowerShell blocks `.ps1` scripts.** Use the `.cmd` variants (`scripts\doctor.cmd`, `scripts\run_checks.cmd`) or run with `powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1`.
- **Ports already in use.** `scripts\doctor.cmd` warns about busy ports. Change the `*_HOST_PORT` variables in `.env` to free host ports.
- **Docker Hub download fails (`EOF`).** If a pre-built local Airflow image exists, fall back to the offline base stack: `docker compose -f docker-compose.local-airflow.yml up -d`.
- **WSL errors.** Update WSL from an elevated PowerShell with `wsl --update`, then restart Docker Desktop.
- **Superset fails to start.** `SUPERSET_SECRET_KEY` is missing from `.env`; add it and recreate the service.
- **Jupyter token rejected.** Get the token with `docker exec de-demo-jupyter jupyter server list` (map container port `8888` to host port `18888`).
- **Out of memory.** Close other Docker containers or increase Docker Desktop's allocated memory.

More diagnostics are in [troubleshooting.md](troubleshooting.md) and the [README](../README.md).

## Next steps

- [ARCHITECTURE.md](ARCHITECTURE.md) — how the components fit together.
- [CONFIGURATION.md](CONFIGURATION.md) — all environment variables and component settings.
- [DEVELOPMENT.md](DEVELOPMENT.md) — building and extending the pipeline.
- [TESTING.md](TESTING.md) — quality checks and verification jobs.
- [DEPLOYMENT.md](DEPLOYMENT.md) — running the stack and recovering state.
