# Quickstart for Windows

Use this guide to create the local demo and generate its quality report.

## 1. Install the tools

Install these required tools:

- Docker Desktop for Windows
- Git
- uv 0.12.5

Install the exact uv release:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/0.12.5/install.ps1 | iex"
uv --version  # must report uv 0.12.5
```

These tools are optional:

- VS Code or PyCharm
- DBeaver for PostgreSQL access

If Docker Desktop asks you to sign in, sign in or create an account. You do not need to publish images.

## 2. Make sure that Docker works

Start Docker Desktop. Wait until the Docker engine is ready.

Run these commands in PowerShell:

```powershell
docker --version
docker compose version
```

If Docker reports a WSL error, open PowerShell as an administrator. Then run:

```powershell
wsl --update
```

Restart Docker Desktop after the update.

## 3. Clone the repository

```powershell
cd D:\
git clone https://github.com/dim4eg91/de_practicum_demo.git de_practicum_demo
cd D:\de_practicum_demo
```

Make sure that the current directory is the repository root:

```powershell
Get-Item docker-compose.yml
```

If the file does not exist, change to the correct directory before you continue.

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

For this local demo, set the secret values in `.env`. Git ignores this file.

## 4. Run the doctor script

```powershell
scripts\doctor.cmd
```

The script reports the state of Docker, Compose, CSV files, and ports `15432` and `18085`.

## 5. Start the demo

```powershell
docker compose up -d
```

If Docker Hub returns an `EOF` error, use the local Airflow fallback:

```powershell
docker compose -f docker-compose.local-airflow.yml up -d
```

Use this fallback only when the local Airflow image already exists.

Display the container state:

```powershell
docker compose ps
```

The expected state is:

- `de-demo-postgres` is healthy.
- `de-demo-airflow` is running.

## 6. Display the initial data layers

```powershell
scripts\show_layers.cmd
```

Before the DAG runs, the `stg`, `core`, and `marts` layers must be empty.

## 7. Run the DAG

Open Airflow:

```text
http://localhost:18085
```

No login is required. The local demo uses Airflow 3.3.1 Simple Auth Manager in
all-admin mode, and Compose exposes the UI only on `127.0.0.1`.

SQLite metadata and LocalExecutor are intentional for this local practicum;
do not use this deployment shape for production.

In Airflow:

1. Find `demo_core_marts_pipeline`.
2. Enable the DAG.
3. Select **Trigger DAG**.
4. Wait for the `success` state.

## 8. Run the data checks

```powershell
scripts\run_checks.cmd
```

The expected results are:

- The `stg`, `core`, and `marts` layers contain rows.
- Duplicate grain rows equal `0`.
- Null keys equal `0`.
- The reconciliation difference equals `0.00`.
- The smoke status is `success`.

## 9. Build the report

```powershell
scripts\build_report.cmd
```

Open the generated report:

```text
reports\demo_quality_report.html
```

The repository also contains these data-model files:

- `docs\schema.md`
- `docs\dbdiagram_overview.dbml`
- `docs\dbdiagram_demo.dbml`

## 10. Complete the exercises

Open `docs\exercises.md`. It contains these exercises:

- Build a SQL payment mart.
- Add an Airflow quality gate.

Run the exercise checks:

```powershell
scripts\check_task_sql.cmd
scripts\check_task_airflow.cmd
```

## 11. Stop the demo

```powershell
docker compose down
```

CAUTION: The next command deletes all demo data.

```powershell
docker compose down -v
```
