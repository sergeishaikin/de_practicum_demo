@echo off
setlocal

echo Checking that Airflow sees task check_payment_reconcile ...
docker compose exec -T de-demo-airflow airflow tasks list warehouse_marts_validation | findstr /C:"quality.check_payment_reconcile" >nul
if errorlevel 1 (
  echo Task quality.check_payment_reconcile was not found in warehouse_marts_validation.
  echo Add it to dags\warehouse_orders.py between validate_marts and publish_mart_assets.
  exit /b 1
)

echo.
echo Running the actual payment callable through its Gherkin feature test.
uv run --locked pytest tests\features\test_airflow_workflow_behavior.py -m "bdd and airflow" -k "payment_match_allows_mart_publication" -q
if errorlevel 1 exit /b 1

echo.
echo Airflow feature test passed.
