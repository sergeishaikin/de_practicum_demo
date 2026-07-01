#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

for check in \
  /demo_sql/00_layer_snapshot.sql \
  /demo_sql/01_grain_checks.sql \
  /demo_sql/02_null_keys.sql \
  /demo_sql/03_reconcile.sql \
  /demo_sql/04_audit_smoke.sql \
  /demo_sql/05_quality_scorecard.sql
do
  echo
  echo "== $check =="
  docker compose exec -T de-demo-postgres psql -U app -d dwh -f "$check"
done
