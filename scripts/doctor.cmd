@echo off
setlocal
set FAIL=0

if not exist docker-compose.yml (
  echo [FAIL] docker-compose.yml not found. Run this script from the project root.
  exit /b 1
)
echo [OK] Project root detected.

where docker >nul 2>nul
if errorlevel 1 (
  echo [FAIL] Docker CLI not found.
  set FAIL=1
) else (
  echo [OK] Docker CLI found.
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo [FAIL] Docker Compose v2 is not available.
  set FAIL=1
) else (
  echo [OK] Docker Compose found.
)

docker info >nul 2>nul
if errorlevel 1 (
  echo [FAIL] Docker engine does not respond. Start Docker Desktop first.
  set FAIL=1
) else (
  echo [OK] Docker engine responds.
)

docker compose config >nul 2>nul
if errorlevel 1 (
  echo [FAIL] docker-compose.yml is not valid.
  set FAIL=1
) else (
  echo [OK] Compose config is valid.
)

for %%F in (
  data\raw\olist_orders_dataset.csv
  data\raw\olist_order_items_dataset.csv
  data\raw\olist_order_payments_dataset.csv
  data\raw\olist_customers_dataset.csv
) do (
  if not exist %%F (
    echo [FAIL] Missing %%F
    set FAIL=1
  ) else (
    echo [OK] Found %%F
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports = @(15432, 18085); foreach ($p in $ports) { $busy = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; if ($busy) { Write-Host \"[WARN] Port $p is already in use. If demo is already running, this is ok.\" } else { Write-Host \"[OK] Port $p is free.\" } }"

if not "%FAIL%"=="0" (
  echo.
  echo Doctor found problems. Fix them before running the demo.
  exit /b 1
)

echo.
echo Current Compose containers:
docker compose ps

echo.
echo Doctor passed.
