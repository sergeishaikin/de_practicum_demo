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
with telemetry.span('ng05.m2.acceptance', {'lakehouse.load_id': 'ng05-m2-exemplar-acceptance', 'lakehouse.source': 'writer'}) as span:
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


def main() -> int:
    tempo = os.getenv("NG05_TEMPO_URL", "http://localhost:13200")
    prometheus = os.getenv("NG05_PROMETHEUS_URL", "http://localhost:19090")
    wait_http(f"{tempo}/ready")
    wait_collector()
    trace_id = start_writer()
    try:
        query = urllib.parse.quote(
            '{ .lakehouse.load_id = "ng05-m2-exemplar-acceptance" }', safe=""
        )
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                trace = get_json(f"{tempo}/api/traces/{trace_id}")
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
        print(
            json.dumps(
                {
                    "tempo_ready": True,
                    "trace_id": trace_id,
                    "traceql_match": True,
                    "prometheus_exemplar_match": True,
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
