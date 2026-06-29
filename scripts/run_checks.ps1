$ErrorActionPreference = "Stop"

$checks = @(
  "/demo_sql/00_layer_snapshot.sql",
  "/demo_sql/01_grain_checks.sql",
  "/demo_sql/02_null_keys.sql",
  "/demo_sql/03_reconcile.sql",
  "/demo_sql/04_audit_smoke.sql",
  "/demo_sql/05_quality_scorecard.sql"
)

foreach ($check in $checks) {
  Write-Host ""
  Write-Host "== $check =="
  docker compose exec -T de-demo-postgres psql -U app -d dwh -f $check
}
