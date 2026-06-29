@echo off
setlocal

for %%F in (
  /demo_sql/00_layer_snapshot.sql
  /demo_sql/01_grain_checks.sql
  /demo_sql/02_null_keys.sql
  /demo_sql/03_reconcile.sql
  /demo_sql/04_audit_smoke.sql
  /demo_sql/05_quality_scorecard.sql
) do (
  echo.
  echo == %%F ==
  docker compose exec -T de-demo-postgres psql -U app -d dwh -f %%F
)
