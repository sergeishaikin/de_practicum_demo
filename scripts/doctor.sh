#!/usr/bin/env sh
set -eu

# Keep container paths like /demo_sql/... intact when scripts run in Git Bash on Windows.
export MSYS_NO_PATHCONV=1

fail=0

ok() { echo "[OK] $1"; }
warn() { echo "[WARN] $1"; }
fail_msg() { echo "[FAIL] $1"; fail=1; }

if [ ! -f docker-compose.yml ]; then
  echo "[FAIL] docker-compose.yml not found. Run this script from the project root."
  exit 1
fi
ok "Project root detected."

if command -v docker >/dev/null 2>&1; then
  ok "Docker CLI found."
else
  fail_msg "Docker CLI not found."
fi

if docker compose version >/dev/null 2>&1; then
  ok "Docker Compose found."
else
  fail_msg "Docker Compose v2 is not available."
fi

if docker info >/dev/null 2>&1; then
  ok "Docker engine responds."
else
  fail_msg "Docker engine does not respond. Start Docker Desktop first."
fi

if docker compose config >/dev/null 2>&1; then
  ok "Compose config is valid."
else
  fail_msg "docker-compose.yml is not valid."
fi

for file in \
  data/raw/olist_orders_dataset.csv \
  data/raw/olist_order_items_dataset.csv \
  data/raw/olist_order_payments_dataset.csv \
  data/raw/olist_customers_dataset.csv
do
  if [ -f "$file" ]; then
    ok "Found $file"
  else
    fail_msg "Missing $file"
  fi
done

check_port() {
  port="$1"
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      warn "Port $port is already in use. If demo is already running, this is ok."
    else
      ok "Port $port is free."
    fi
  elif command -v nc >/dev/null 2>&1; then
    if nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
      warn "Port $port is already in use. If demo is already running, this is ok."
    else
      ok "Port $port is free."
    fi
  else
    warn "Cannot check port $port: lsof/nc not found."
  fi
}

check_port 15432
check_port 18085

if [ "$fail" -ne 0 ]; then
  echo
  echo "Doctor found problems. Fix them before running the demo."
  exit 1
fi

echo
echo "Current Compose containers:"
docker compose ps || true

echo
echo "Doctor passed."
