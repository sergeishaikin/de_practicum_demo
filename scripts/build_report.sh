#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

if ! docker compose exec -T de-demo-postgres psql -U app -d dwh -c "select 1 as ok;" >/dev/null 2>&1; then
  echo "Postgres is not running. Start the demo first:"
  echo "docker compose up -d"
  echo "or:"
  echo "docker compose -f docker-compose.local-airflow.yml up -d"
  exit 1
fi

mkdir -p reports
REPORT="reports/demo_quality_report.html"

cat > "$REPORT" <<'HTML'
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>DE Practicum Demo Report</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#172026;background:#f6f8fb;}
h1{margin:0 0 8px;font-size:28px;} h2{margin:28px 0 10px;font-size:18px;}
.lead{color:#52616b;margin:0 0 24px;} .section{background:#fff;border:1px solid #d9e1e8;border-radius:8px;padding:18px;margin:16px 0;}
table{border-collapse:collapse;width:100%;font-size:14px;background:#fff;} th,td{border:1px solid #d9e1e8;padding:8px 10px;text-align:left;} th{background:#eef3f7;}
.hint{color:#52616b;font-size:13px;margin-top:10px;} code{background:#eef3f7;padding:2px 4px;border-radius:4px;}
</style>
</head>
<body>
<h1>DE Practicum Demo Report</h1>
<p class="lead">CSV files were loaded into <code>stg</code>, transformed into <code>core</code>, and exposed as <code>marts</code>. This report focuses on pipeline stages and data quality, not business BI.</p>
HTML

section() {
  title="$1"
  sql_file="$2"
  {
    printf '<div class="section">\n'
    printf '<h2>%s</h2>\n' "$title"
    docker compose exec -T de-demo-postgres psql -U app -d dwh -H -P border=0 -P tableattr=class=data-table -f "$sql_file"
    printf '</div>\n'
  } >> "$REPORT"
}

section "Layer snapshot" "/demo_sql/00_layer_snapshot.sql"
section "Quality scorecard" "/demo_sql/05_quality_scorecard.sql"
section "Grain checks" "/demo_sql/01_grain_checks.sql"
section "Null key checks" "/demo_sql/02_null_keys.sql"
section "Reconcile" "/demo_sql/03_reconcile.sql"
section "Audit smoke" "/demo_sql/04_audit_smoke.sql"
section "Mart preview" "/demo_sql/06_mart_preview.sql"

cat >> "$REPORT" <<'HTML'
<p class="hint">Generated from local Postgres via Docker Compose.</p>
</body></html>
HTML

echo "Report created: $(pwd)/$REPORT"
