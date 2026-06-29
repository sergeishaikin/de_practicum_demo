@echo off
setlocal

echo Applying db\tasks\01_create_payment_type_daily.sql ...
docker compose exec -T de-demo-postgres psql -U app -d dwh -v ON_ERROR_STOP=1 -f /tasks/01_create_payment_type_daily.sql
if errorlevel 1 exit /b 1

echo.
echo Checking SQL task ...
docker compose exec -T de-demo-postgres psql -U app -d dwh -v ON_ERROR_STOP=1 -f /task_checks/01_check_payment_type_daily.sql
if errorlevel 1 exit /b 1

echo.
echo SQL task passed.
