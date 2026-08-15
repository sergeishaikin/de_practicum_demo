#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${AIRFLOW_DB_USER:?AIRFLOW_DB_USER is required}"
: "${AIRFLOW_DB_PASSWORD:?AIRFLOW_DB_PASSWORD is required}"
: "${AIRFLOW_DB_NAME:?AIRFLOW_DB_NAME is required}"

export PGPASSWORD="$POSTGRES_PASSWORD"

psql --username "$POSTGRES_USER" --dbname postgres \
  --set=airflow_user="$AIRFLOW_DB_USER" \
  --set=airflow_password="$AIRFLOW_DB_PASSWORD" \
  --set=airflow_db="$AIRFLOW_DB_NAME" \
  --set=ON_ERROR_STOP=1 <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'airflow_user', :'airflow_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'airflow_user') \gexec

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'airflow_user', :'airflow_password') \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'airflow_db', :'airflow_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'airflow_db') \gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'airflow_db', :'airflow_user') \gexec
SQL
