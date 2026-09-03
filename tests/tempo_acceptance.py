"""Bounded live acceptance for the optional NG-0.5 Tempo capability."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_IMAGE = "de-practicum-demo-iceberg:0.11.1-h1"
NETWORK = "de_demo_net"
WRITER = "ng05-tempo-acceptance-writer"
CANONICAL = "ng05-tempo-canonical-minio"
MINIO_IMAGE = "minio/minio@sha256:a1ea29fa28355559ef137d71fc570e508a214ec84ff8083e39bc5428980b015e"
MC_IMAGE = (
    "minio/mc@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727"
)


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], cwd=ROOT, text=True, capture_output=True, timeout=60
    )
    if check and result.returncode:
        raise RuntimeError(
            f"docker {' '.join(args)} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode())


def get_json_auth(url: str, password: str) -> dict:
    token = base64.b64encode(f"admin:{password}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode())


def wait_http(url: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2).close()
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"timed out waiting for {url}")


def wait_collector(timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = docker(
            "inspect",
            "-f",
            "{{.State.Health.Status}}",
            "de-demo-otel-collector",
            check=False,
        ).strip()
        if status == "healthy":
            return
        time.sleep(1)
    raise TimeoutError("otel-collector did not become healthy")


def start_writer() -> str:
    code = """
import sys, time
sys.path.insert(0, '/app/iceberg')
from common.telemetry import setup_telemetry
from common.ops import _RuntimeMetrics
telemetry = setup_telemetry('iceberg-writer')
runtime = _RuntimeMetrics('9101')
with telemetry.span('ng05.m2.acceptance', {
    'lakehouse.load_id': 'ng05-m2-exemplar-acceptance',
    'lakehouse.source': 'writer',
    'authorization': 'Bearer super-secret-token',
    'password': 'do-not-store',
    'db.statement': 'select customer_email from orders',
}) as span:
    print('TRACE_ID=' + f'{span.get_span_context().trace_id:032x}', flush=True)
    runtime.observe(source='writer', status='success', duration_ms=250,
        work_available=1, work_in_flight=0, work_completed=1,
        rows_processed=1, files_processed=1, keys_processed=1,
        lower_versions_ignored=0, ff14_conflicts=0, shadow_mismatches=0,
        silver_duration_ms=10, gold_duration_ms=5,
        files_planned=1, files_removed=0, files_added=1,
        bytes_planned=100, bytes_removed=0, bytes_added=100)
if telemetry._tracer_provider is not None:
    telemetry._tracer_provider.force_flush(5000)
time.sleep(45)
"""
    encoded = base64.b64encode(code.encode()).decode()
    docker(
        "run",
        "-d",
        "--name",
        WRITER,
        "--network",
        NETWORK,
        "--network-alias",
        "iceberg-writer",
        "-e",
        "OTEL_ENABLED=1",
        "-e",
        "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317",
        "-e",
        "PROMETHEUS_METRICS_PORT=9101",
        "-v",
        f"{ROOT / 'iceberg'}:/app/iceberg:ro",
        APP_IMAGE,
        "python",
        "-c",
        f"import base64; exec(base64.b64decode('{encoded}'))",
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        logs = docker("logs", WRITER, check=False)
        for line in logs.splitlines():
            if line.startswith("TRACE_ID="):
                return line.split("=", 1)[1].strip()
        time.sleep(1)
    raise TimeoutError(f"{WRITER} did not emit a trace ID")


def storage_isolation() -> None:
    docker(
        "run",
        "-d",
        "--name",
        CANONICAL,
        "--network",
        NETWORK,
        "--network-alias",
        "canonical-minio",
        "-e",
        "MINIO_ROOT_USER=canonical-root",
        "-e",
        "MINIO_ROOT_PASSWORD=canonical-secret",
        MINIO_IMAGE,
        "server",
        "/data",
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            probe = docker(
                "run",
                "--rm",
                "--network",
                NETWORK,
                MC_IMAGE,
                "alias",
                "set",
                "canonical",
                "http://canonical-minio:9000",
                "canonical-root",
                "canonical-secret",
                check=False,
            )
            if "successfully" in probe.lower():
                break
            time.sleep(1)
        else:
            raise TimeoutError("canonical disposable MinIO did not become ready")
        positive = docker(
            "run",
            "--rm",
            "--network",
            NETWORK,
            "--entrypoint",
            "/bin/sh",
            MC_IMAGE,
            "-c",
            "mc alias set tempo http://tempo-minio:9000 tempo-demo replace-with-a-random-tempo-secret && "
            "mc mb --ignore-existing tempo/tempo-traces && printf proof | mc pipe tempo/tempo-traces/ng05/isolation-proof",
            check=False,
        )
        if "error" in positive.lower():
            raise AssertionError(f"Tempo credential positive write failed: {positive}")
        negative = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                NETWORK,
                "--entrypoint",
                "/bin/sh",
                MC_IMAGE,
                "-c",
                "mc alias set canonical http://canonical-minio:9000 tempo-demo replace-with-a-random-tempo-secret >/dev/null && "
                "mc mb canonical/iceberg-ng05-denied",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if negative.returncode == 0:
            raise AssertionError(
                "Tempo credentials unexpectedly wrote canonical namespace"
            )
        print("storage_positive=tempo-traces/ng05/isolation-proof")
        print("storage_negative=DENIED canonical/iceberg-ng05-denied")
    finally:
        docker("rm", "-f", CANONICAL, check=False)


def main() -> int:
    tempo = os.getenv("NG05_TEMPO_URL", "http://localhost:13200")
    prometheus = os.getenv("NG05_PROMETHEUS_URL", "http://localhost:19090")
    grafana = os.getenv("NG05_GRAFANA_URL")
    grafana_password = os.getenv("NG05_GRAFANA_PASSWORD", "ng05-grafana-secret")
    wait_http(f"{tempo}/ready")
    wait_collector()
    trace_id = start_writer()
    try:
        storage_isolation()
        query = urllib.parse.quote(
            '{ .lakehouse.load_id = "ng05-m2-exemplar-acceptance" }', safe=""
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                trace = get_json(f"{tempo}/api/traces/{trace_id}")
                encoded = json.dumps(trace)
                if any(
                    secret in encoded
                    for secret in ("super-secret-token", "do-not-store")
                ):
                    raise AssertionError("forbidden trace attribute survived redaction")
                if "ng05-m2-exemplar-acceptance" not in encoded:
                    raise AssertionError("safe load_id was removed by redaction")
                search = get_json(f"{tempo}/api/search?q={query}&limit=20")
                ids = {row["traceID"] for row in search.get("traces", [])}
                exemplar = get_json(
                    f"{prometheus}/api/v1/query_exemplars?query="
                    + urllib.parse.quote("lakehouse_duration_seconds_bucket", safe="")
                )
                labels = [
                    ex.get("labels", {}).get("trace_id")
                    for series in exemplar.get("data", [])
                    for ex in series.get("exemplars", [])
                ]
                if trace and trace_id in ids and trace_id in labels:
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            raise AssertionError(
                f"TraceQL/exemplar did not return {trace_id} after bounded wait"
            )
        if grafana:
            health = get_json_auth(f"{grafana}/api/health", grafana_password)
            if health.get("database") != "ok":
                raise AssertionError(f"Grafana health failed: {health}")
            datasources = get_json_auth(f"{grafana}/api/datasources", grafana_password)
            uids = {item.get("uid") for item in datasources}
            if {"prometheus", "tempo"} - uids:
                raise AssertionError(f"Grafana datasource UIDs missing: {uids}")
            ids_by_uid = {item["uid"]: item["id"] for item in datasources}
            grafana_trace = get_json_auth(
                f"{grafana}/api/datasources/proxy/{ids_by_uid['tempo']}/api/traces/{trace_id}",
                grafana_password,
            )
            if not grafana_trace:
                raise AssertionError("Grafana Tempo proxy returned an empty trace")
            grafana_exemplars = get_json_auth(
                f"{grafana}/api/datasources/proxy/{ids_by_uid['prometheus']}/api/v1/query_exemplars?query="
                + urllib.parse.quote("lakehouse_duration_seconds_bucket", safe=""),
                grafana_password,
            )
            grafana_labels = [
                ex.get("labels", {}).get("trace_id")
                for series in grafana_exemplars.get("data", [])
                for ex in series.get("exemplars", [])
            ]
            if trace_id not in grafana_labels:
                raise AssertionError(
                    "Grafana Prometheus proxy returned a different exemplar"
                )
        print(
            json.dumps(
                {
                    "tempo_ready": True,
                    "trace_id": trace_id,
                    "traceql_match": True,
                    "trace_redaction": True,
                    "prometheus_exemplar_match": True,
                    "grafana_correlation": bool(grafana),
                    "service": "iceberg-writer",
                    "load_id": "ng05-m2-exemplar-acceptance",
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        docker("rm", "-f", WRITER, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
