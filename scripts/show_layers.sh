#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

docker compose exec -T de-demo-postgres psql -U app -d dwh -f /demo_sql/00_layer_snapshot.sql
