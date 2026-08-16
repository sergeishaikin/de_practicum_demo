#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

run_uv() {
  uvx --from uv==0.12.5 uv --quiet "$@"
}

run_uv lock
run_uv export --locked --only-group dev --no-emit-project --output-file requirements-dev.txt
run_uv pip compile \
  --universal \
  --generate-hashes \
  --python-version 3.12 \
  --constraint airflow.constraints.txt \
  --output-file airflow.requirements.txt \
  airflow.requirements.in

compile() {
  python_version="$1"
  input="$2"
  output="$3"
  run_uv pip compile \
    --universal \
    --generate-hashes \
    --python-version "$python_version" \
    --output-file "$output" \
    "$input"
}

compile 3.12 dbt/requirements.in dbt/requirements.txt
compile 3.12 dbt/warehouse/requirements.in dbt/warehouse/requirements.txt
compile 3.12 iceberg/requirements.in iceberg/requirements.txt
compile 3.10 jupyter/requirements.in jupyter/requirements.txt
compile 3.12 kafka/producer/requirements.in kafka/producer/requirements.txt
compile 3.12 observability/requirements.in observability/requirements.txt
compile 3.12 spark/requirements.in spark/requirements.txt
