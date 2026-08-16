# Quickstart for macOS and Linux

Use this guide to create the local demo and generate its quality report.

## 1. Install the tools

Install these required tools:

- Docker Desktop, or Docker Engine with Docker Compose v2
- Git
- uv 0.12.5

Install the exact uv release:

```bash
curl -LsSf https://astral.sh/uv/0.12.5/install.sh | sh
uv --version  # must report uv 0.12.5
```

These tools are optional:

- VS Code or PyCharm
- DBeaver for PostgreSQL access

Docker Desktop is the simplest option on macOS. On Linux, use Docker Compose v2 through the `docker compose` command.

## 2. Make sure that Docker works

Start Docker Desktop or Docker Engine.

```bash
docker --version
docker compose version
docker info
```

If `docker info` fails, correct the Docker error before you continue.

## 3. Clone the repository

```bash
git clone https://github.com/dim4eg91/de_practicum_demo.git de_practicum_demo
cd de_practicum_demo
```

Make sure that the current directory is the repository root:

```bash
ls docker-compose.yml
```

If the file does not exist, change to the correct directory before you continue.

Create the local environment file:

```bash
cp .env.example .env
```

Replace `AIRFLOW_API_SECRET_KEY`, `AIRFLOW_JWT_SECRET`, and
`AIRFLOW_DB_PASSWORD` with independent random URL-safe values. Git ignores
this file.

## 4. Run the doctor script

```bash
bash scripts/doctor.sh
```

The script reports the state of Docker, Compose, CSV files, and ports `15432` and `18085`.

## 5. Start the demo

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml up -d
```

Display the container state:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml ps
```

The expected state is:

- `de-demo-postgres` is healthy.
- `de-demo-airflow` is running.

## 6. Display the initial data layers

```bash
bash scripts/show_layers.sh
```

Before the DAG runs, the `stg`, `core`, and `marts` layers must be empty.

## 7. Run the DAG

Open Airflow:

```text
http://localhost:18085
```

No login is required. The local demo uses Airflow 3.3.1 Simple Auth Manager in
all-admin mode, and Compose exposes the UI only on `127.0.0.1`.

Airflow metadata persists in a dedicated PostgreSQL database, while
LocalExecutor remains intentional for this local practicum. Do not use this
deployment shape for production.

In Airflow:

1. Find and enable `warehouse_marts_validation`.
2. Find `warehouse_orders_ingestion` and select **Trigger DAG**.
3. Wait for ingestion to succeed and publish the `core.orders` Asset.
4. Confirm that `warehouse_marts_validation` starts automatically and succeeds.
5. Do not manually trigger the downstream DAG.

## 8. Run the data checks

```bash
bash scripts/run_checks.sh
```

The expected results are:

- The `stg`, `core`, and `marts` layers contain rows.
- Duplicate grain rows equal `0`.
- Null keys equal `0`.
- The reconciliation difference equals `0.00`.
- The smoke status is `success`.

## 9. Build the report

```bash
bash scripts/build_report.sh
```

On macOS, open the report with:

```bash
open reports/demo_quality_report.html
```

On Linux, open the report with:

```bash
xdg-open reports/demo_quality_report.html
```

## 10. Complete the exercises

Open `docs/exercises.md`. It contains these exercises:

- Build a SQL payment mart.
- Add an Airflow quality gate.

Run the exercise checks:

```bash
bash scripts/check_task_sql.sh
bash scripts/check_task_airflow.sh
```

## 11. Stop the demo

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml down
```

CAUTION: The next command deletes all demo data.

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml down -v
```
