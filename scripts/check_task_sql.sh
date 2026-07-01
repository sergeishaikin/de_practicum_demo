#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

echo "Applying db/tasks/01_create_payment_type_daily.sql ..."
docker compose exec -T de-demo-postgres psql -U app -d dwh -v ON_ERROR_STOP=1 -f /tasks/01_create_payment_type_daily.sql

echo
echo "Checking SQL task ..."
docker compose exec -T de-demo-postgres psql -U app -d dwh -v ON_ERROR_STOP=1 -f /task_checks/01_check_payment_type_daily.sql

echo
echo "SQL task passed."
