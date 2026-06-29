@echo off
setlocal

docker compose exec -T de-demo-postgres psql -U app -d dwh -c "select 1 as ok;" >nul 2>nul
if errorlevel 1 (
  echo Postgres is not running. Start the demo first:
  echo docker compose up -d
  echo or:
  echo docker compose -f docker-compose.local-airflow.yml up -d
  exit /b 1
)

if not exist reports mkdir reports
set REPORT=reports\demo_quality_report.html

> "%REPORT%" echo ^<!doctype html^>
>> "%REPORT%" echo ^<html lang="ru"^>
>> "%REPORT%" echo ^<head^>
>> "%REPORT%" echo ^<meta charset="utf-8"^>
>> "%REPORT%" echo ^<title^>DE Practicum Demo Report^</title^>
>> "%REPORT%" echo ^<style^>
>> "%REPORT%" echo body{font-family:Segoe UI,Arial,sans-serif;margin:32px;color:#172026;background:#f6f8fb;}
>> "%REPORT%" echo h1{margin:0 0 8px;font-size:28px;} h2{margin:28px 0 10px;font-size:18px;}
>> "%REPORT%" echo .lead{color:#52616b;margin:0 0 24px;} .section{background:#fff;border:1px solid #d9e1e8;border-radius:8px;padding:18px;margin:16px 0;}
>> "%REPORT%" echo table{border-collapse:collapse;width:100%%;font-size:14px;background:#fff;} th,td{border:1px solid #d9e1e8;padding:8px 10px;text-align:left;} th{background:#eef3f7;}
>> "%REPORT%" echo .hint{color:#52616b;font-size:13px;margin-top:10px;} code{background:#eef3f7;padding:2px 4px;border-radius:4px;}
>> "%REPORT%" echo ^</style^>
>> "%REPORT%" echo ^</head^>
>> "%REPORT%" echo ^<body^>
>> "%REPORT%" echo ^<h1^>DE Practicum Demo Report^</h1^>
>> "%REPORT%" echo ^<p class="lead"^>CSV files were loaded into ^<code^>stg^</code^>, transformed into ^<code^>core^</code^>, and exposed as ^<code^>marts^</code^>. This report focuses on pipeline stages and data quality, not business BI.^</p^>

call :section "Layer snapshot" "/demo_sql/00_layer_snapshot.sql"
call :section "Quality scorecard" "/demo_sql/05_quality_scorecard.sql"
call :section "Grain checks" "/demo_sql/01_grain_checks.sql"
call :section "Null key checks" "/demo_sql/02_null_keys.sql"
call :section "Reconcile" "/demo_sql/03_reconcile.sql"
call :section "Audit smoke" "/demo_sql/04_audit_smoke.sql"
call :section "Mart preview" "/demo_sql/06_mart_preview.sql"

>> "%REPORT%" echo ^<p class="hint"^>Generated from local Postgres via Docker Compose.^</p^>
>> "%REPORT%" echo ^</body^>^</html^>

echo Report created: %CD%\%REPORT%
exit /b 0

:section
>> "%REPORT%" echo ^<div class="section"^>
>> "%REPORT%" echo ^<h2^>%~1^</h2^>
docker compose exec -T de-demo-postgres psql -U app -d dwh -H -P border=0 -P tableattr=class=data-table -f %~2 >> "%REPORT%"
>> "%REPORT%" echo ^</div^>
exit /b 0
