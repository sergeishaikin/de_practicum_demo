#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

echo "Checking that Airflow sees task check_payment_reconcile ..."
if ! docker compose exec -T de-demo-airflow airflow tasks list warehouse_marts_validation | grep -q "quality.check_payment_reconcile"; then
  echo "Task quality.check_payment_reconcile was not found in warehouse_marts_validation."
  echo "Add it to dags/warehouse_orders.py between validate_marts and publish_mart_assets."
  exit 1
fi

echo
echo "Running the actual payment callable through its Gherkin feature test."
uv run --locked pytest tests/features/test_airflow_workflow_behavior.py \
  -m "bdd and airflow" -k "payment_match_allows_mart_publication" -q

echo
echo "Airflow feature test passed."
