"""Bounded live acceptance for the optional NG-0.6 Loki capability."""

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
NETWORK = "de_demo_net"
WRITER = "ng06-loki-acceptance-writer"
APP_IMAGE = "de-practicum-demo-iceberg:0.11.1-h1"
LOKI_IMAGE = os.getenv("LOKI_IMAGE", "grafana/loki")
MC_IMAGE = os.getenv("LOKI_MINIO_MC_IMAGE", "minio/mc")


def docker_result(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], cwd=ROOT, text=True, capture_output=True, timeout=60
    )


def docker(*args: str, check: bool = True) -> str:
    result = docker_result(*args)
    if check and result.returncode:
        raise RuntimeError(
            f"docker {' '.join(args)} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def wait_http(url: str, timeout: float = 45) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2).close()
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError(f"timed out waiting for {url}")


def loki_query(url: str, query: str) -> list[dict]:
    encoded = urllib.parse.urlencode({"query": query, "limit": "100"})
    with urllib.request.urlopen(
        f"{url}/loki/api/v1/query_range?{encoded}", timeout=10
    ) as response:
        payload = json.loads(response.read().decode())
    return payload.get("data", {}).get("result", [])


def start_writer() -> str:
    code = """
import time, sys
sys.path.insert(0, '/app/iceberg')
from common.telemetry import setup_telemetry
telemetry = setup_telemetry('loki-acceptance')
with telemetry.span('ng06.same-trace', {'lakehouse.load_id': 'ng06-loki-load-001'}) as span:
    trace_id = f'{span.get_span_context().trace_id:032x}'
    telemetry.log('safe acceptance event', attributes={
        'lakehouse.load_id': 'ng06-loki-load-001',
        'authorization': 'Bearer super-secret-token',
        'password': 'do-not-store',
        'db.statement': 'select customer_email from orders',
    })
    print('TRACE_ID=' + trace_id, flush=True)
if telemetry._logger_provider is not None:
    telemetry._logger_provider.force_flush(5000)
if telemetry._tracer_provider is not None:
    telemetry._tracer_provider.force_flush(5000)
time.sleep(10)
"""
    encoded = base64.b64encode(code.encode()).decode()
    docker(
        "run",
        "-d",
        "--name",
        WRITER,
        "--network",
        NETWORK,
        "-e",
        "OTEL_ENABLED=1",
        "-e",
        "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317",
        "-e",
        "OTEL_SERVICE_NAMESPACE=de-practicum",
        "-e",
        "OTEL_DEPLOYMENT_ENVIRONMENT=local",
        "-v",
        f"{ROOT / 'iceberg'}:/app/iceberg:ro",
        APP_IMAGE,
        "python",
        "-c",
        f"import base64; exec(base64.b64decode('{encoded}'))",
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        logs = docker("logs", WRITER, check=False)
        for line in logs.splitlines():
            if line.startswith("TRACE_ID="):
                return line.split("=", 1)[1].strip()
        time.sleep(1)
    raise TimeoutError("acceptance writer did not emit a trace ID")


def storage_isolation() -> None:
    access = os.environ["LOKI_S3_ACCESS_KEY"]
    secret = os.environ["LOKI_S3_SECRET_KEY"]
    bucket = os.getenv("LOKI_S3_BUCKET", "loki-logs")
    positive = docker_result(
        "run",
        "--rm",
        "--network",
        NETWORK,
        "--entrypoint",
        "/bin/sh",
        "--env",
        f"ACCESS={access}",
        "--env",
        f"SECRET={secret}",
        MC_IMAGE,
        "-c",
        'mc alias set loki http://loki-minio:9000 "$ACCESS" "$SECRET" >/dev/null && '
        f"mc mb --ignore-existing loki/{bucket} && printf proof | mc pipe loki/{bucket}/ng06/storage-proof",
    )
    if positive.returncode != 0:
        raise AssertionError("Loki credential positive write failed")
    negative = docker_result(
        "run",
        "--rm",
        "--network",
        NETWORK,
        "--entrypoint",
        "/bin/sh",
        "--env",
        f"ACCESS={access}",
        "--env",
        f"SECRET={secret}",
        MC_IMAGE,
        "-c",
        'mc alias set canonical http://minio:9000 "$ACCESS" "$SECRET" >/dev/null && mc mb canonical/denied',
    )
    if negative.returncode == 0:
        raise AssertionError("Loki credential wrote canonical warehouse namespace")
    print(f"storage_positive={bucket}/ng06/storage-proof")
    print("storage_negative=DENIED canonical/denied")


def main() -> int:
    loki_url = os.getenv("NG06_LOKI_URL", "http://localhost:13100")
    wait_http(f"{loki_url}/ready")
    trace_id = start_writer()
    time.sleep(5)
    results = loki_query(
        loki_url, f'{{service_name="loki-acceptance"}} | trace_id="{trace_id}"'
    )
    if not results:
        raise AssertionError("same trace log was not queryable in Loki")
    text = json.dumps(results)
    for forbidden in (
        "super-secret-token",
        "do-not-store",
        "select customer_email from orders",
    ):
        if forbidden in text:
            raise AssertionError(f"forbidden value persisted in Loki: {forbidden}")
    if "ng06-loki-load-001" not in text or trace_id not in text:
        raise AssertionError("safe load identity or trace ID missing from Loki")
    storage_isolation()
    print(f"same_trace_id={trace_id}")
    print("trace_to_logs=PASS")
    print("persisted_redaction=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        docker("rm", "-f", WRITER, check=False)
