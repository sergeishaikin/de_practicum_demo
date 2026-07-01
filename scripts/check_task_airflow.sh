#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

echo "Checking that Airflow sees task check_payment_reconcile ..."
if ! docker compose exec -T de-demo-airflow airflow tasks list demo_core_marts_pipeline | grep -q "check_payment_reconcile"; then
  echo "Task check_payment_reconcile was not found in demo_core_marts_pipeline."
  echo "Add it to dags/demo_core_marts_pipeline.py and put it between rebuild_core_and_marts and write_audit."
  exit 1
fi

echo
echo "Running DAG test. This executes the pipeline inside Airflow and fails on broken quality gates."
LOGICAL_DATE="$(date '+%Y-%m-%dT%H:%M:%S')"
docker compose exec -T de-demo-airflow airflow dags test demo_core_marts_pipeline "$LOGICAL_DATE"

echo
echo "Airflow task passed."
