"""Idempotent local/CI bootstrap and dependency-aware readiness checks."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from validate_runtime_config import read_env_file


PIPELINE_PROVENANCE_MIGRATION = (
    "/docker-entrypoint-initdb.d/007_pipeline_runs_ingestion_provenance.sql"
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _docker_exec(*args: str, timeout: int = 30) -> str:
    result = _run("docker", "exec", *args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "docker exec failed")
    return result.stdout


def _http_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status == 200
    except OSError:
        return False


def wait_for_stack(values: dict[str, str], deadline: float) -> None:
    checks = {
        "iceberg-rest": f"http://127.0.0.1:{values['ICEBERG_REST_PORT']}/v1/config",
        "trino": f"http://127.0.0.1:{values['TRINO_HOST_PORT']}/v1/info",
        "prometheus": f"http://127.0.0.1:{values['PROMETHEUS_HOST_PORT']}/-/ready",
        "grafana": f"http://127.0.0.1:{values['GRAFANA_HOST_PORT']}/api/health",
    }
    pending = set(checks)
    while pending and time.monotonic() < deadline:
        for name, url in checks.items():
            if name in pending and _http_ready(url):
                pending.remove(name)
        try:
            _docker_exec(
                "de-demo-kafka",
                "/opt/kafka/bin/kafka-topics.sh",
                "--bootstrap-server",
                "localhost:9092",
                "--list",
            )
            pending.discard("kafka")
        except RuntimeError:
            pending.add("kafka")
        if pending:
            time.sleep(5)
    if pending:
        raise RuntimeError(f"stack readiness timed out; pending={sorted(pending)}")


def bootstrap(values: dict[str, str], deadline: float) -> None:
    wait_for_stack(values, deadline)
    alias_deadline = time.monotonic() + min(
        120, max(1, int(deadline - time.monotonic()))
    )
    while time.monotonic() < alias_deadline:
        result = _run(
            "docker",
            "exec",
            "de-demo-minio",
            "mc",
            "alias",
            "set",
            "local",
            "http://localhost:9000",
            values["MINIO_ROOT_USER"],
            values["MINIO_ROOT_PASSWORD"],
        )
        if result.returncode == 0:
            break
        time.sleep(5)
    else:
        raise RuntimeError("MinIO readiness timed out")

    bucket = values.get("MINIO_BUCKET", "de-practicum")
    _docker_exec("de-demo-minio", "mc", "mb", "--ignore-existing", f"local/{bucket}")
    _docker_exec(
        "de-demo-trino",
        "trino",
        "--execute",
        "CREATE SCHEMA IF NOT EXISTS iceberg.bronze; "
        "CREATE SCHEMA IF NOT EXISTS iceberg.silver; "
        "CREATE SCHEMA IF NOT EXISTS iceberg.gold; "
        "CREATE SCHEMA IF NOT EXISTS iceberg.semantic",
    )
    _docker_exec(
        "de-demo-postgres",
        "psql",
        "-X",
        "--set=ON_ERROR_STOP=1",
        "--username",
        values["POSTGRES_USER"],
        "--dbname",
        values["POSTGRES_DB"],
        "--file",
        PIPELINE_PROVENANCE_MIGRATION,
    )
    print(
        "[OK] H1 bootstrap: network, MinIO bucket, catalog schemas, "
        "warehouse migrations, and readiness"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    values = read_env_file(args.env_file)
    values = {
        **values,
        **{key: value for key, value in os.environ.items() if key in values},
    }
    bootstrap(values, time.monotonic() + args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
