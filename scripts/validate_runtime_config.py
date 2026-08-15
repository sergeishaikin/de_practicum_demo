"""Validate the H1 runtime configuration before Compose or deployment."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

IMAGE_KEYS = (
    "POSTGRES_IMAGE",
    "MINIO_IMAGE",
    "METABASE_IMAGE",
    "KAFKA_IMAGE",
    "KAFKA_UI_IMAGE",
    "ICEBERG_REST_IMAGE",
    "TRINO_IMAGE",
    "PROMETHEUS_IMAGE",
    "GRAFANA_IMAGE",
    "SUPERSET_IMAGE",
)
REQUIRED_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "AIRFLOW_DB_NAME",
    "AIRFLOW_DB_USER",
    "AIRFLOW_DB_PASSWORD",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "SUPERSET_SECRET_KEY",
    "AIRFLOW_API_SECRET_KEY",
    "AIRFLOW_JWT_SECRET",
    "GRAFANA_ADMIN_PASSWORD",
)
PORT_KEYS = (
    "POSTGRES_HOST_PORT",
    "AIRFLOW_HOST_PORT",
    "MINIO_API_PORT",
    "MINIO_CONSOLE_PORT",
    "KAFKA_HOST_PORT",
    "ICEBERG_REST_PORT",
    "TRINO_HOST_PORT",
    "PROMETHEUS_HOST_PORT",
    "GRAFANA_HOST_PORT",
)
PLACEHOLDERS = {
    "change-me",
    "replace-with-a-random-deploy-secret",
    "replace-with-a-random-airflow-api-secret",
    "replace-with-a-random-airflow-jwt-secret",
    "replace-with-a-random-airflow-db-password",
    "replace-with-a-deploy-secret",
}


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate(values: dict[str, str], *, profile: str = "clean") -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        value = values.get(key, "")
        if not value:
            errors.append(f"missing required variable: {key}")
        elif value in PLACEHOLDERS:
            errors.append(f"placeholder secret is not deployable: {key}")

    if profile == "clean":
        for key in IMAGE_KEYS:
            value = values.get(key, "")
            if not re.search(r"@sha256:[0-9a-f]{64}$", value):
                errors.append(f"image must be pinned by digest: {key}")

    for key in PORT_KEYS:
        value = values.get(key, "")
        try:
            if not 1 <= int(value) <= 65535:
                raise ValueError
        except ValueError:
            errors.append(f"invalid port: {key}={value!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--profile", choices=("clean", "local"), default="clean")
    args = parser.parse_args()
    values = read_env_file(args.env_file) if args.env_file else {}
    values = {
        **values,
        **{
            key: value
            for key, value in os.environ.items()
            if key in values or not args.env_file
        },
    }
    errors = validate(values, profile=args.profile)
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print(f"[OK] H1 {args.profile} runtime configuration is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
