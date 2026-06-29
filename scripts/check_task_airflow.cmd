@echo off
setlocal

echo Checking that Airflow sees task check_payment_reconcile ...
docker compose exec -T de-demo-airflow airflow tasks list demo_core_marts_pipeline | findstr /C:"check_payment_reconcile" >nul
if errorlevel 1 (
  echo Task check_payment_reconcile was not found in demo_core_marts_pipeline.
  echo Add it to dags\demo_core_marts_pipeline.py and put it between rebuild_core_and_marts and write_audit.
  exit /b 1
)

echo.
echo Running DAG test. This executes the pipeline inside Airflow and fails on broken quality gates.
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-ddTHH:mm:ss"') do set LOGICAL_DATE=%%T
docker compose exec -T de-demo-airflow airflow dags test demo_core_marts_pipeline %LOGICAL_DATE%
if errorlevel 1 exit /b 1

echo.
echo Airflow task passed.
