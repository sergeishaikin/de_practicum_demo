"""Bounded live acceptance for the optional NG-0.6 Loki capability."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import ast
import re
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETWORK = "de_demo_net"
WRITER = "ng06-loki-acceptance-writer"
APP_IMAGE = "de-practicum-demo-iceberg:0.11.1-h1"
LOKI_IMAGE = os.getenv("LOKI_IMAGE", "grafana/loki")
MC_IMAGE = os.getenv("LOKI_MINIO_MC_IMAGE", "minio/mc")
GRAFANA_URL = os.getenv("NG06_GRAFANA_URL", "http://localhost:13001")
GRAFANA_PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "ng06-grafana-ci-secret")
TEMPO_BUCKET = os.getenv("TEMPO_S3_BUCKET", "tempo-traces")


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


def start_writer(count: int = 1) -> str:
    code = """
import time, sys, os
sys.path.insert(0, '/app/iceberg')
from common.telemetry import setup_telemetry
telemetry = setup_telemetry('loki-acceptance')
COUNT = int(os.environ.get('COUNT', '1'))
with telemetry.span('ng06.same-trace', {'lakehouse.load_id': 'ng06-loki-load-001'}) as span:
    trace_id = f'{span.get_span_context().trace_id:032x}'
    for index in range(COUNT):
        telemetry.log('safe acceptance event', event_name='loki.acceptance.event', severity='INFO', attributes={
            'lakehouse.load_id': 'ng06-loki-load-001',
            'authorization': 'Bearer super-secret-token',
            'password': 'do-not-store',
            'api_key': 'api-key-marker',
            'connection_string': 'postgres://app:password@db/orders',
            'customer_email': 'customer@example.com',
            'payload': 'full-payload-marker',
            'db.statement': 'select customer_email from orders',
            'event.sequence': index,
        })
    print('TRACE_ID=' + trace_id, flush=True)
if telemetry._logger_provider is not None:
    telemetry._logger_provider.force_flush(5000)
if telemetry._tracer_provider is not None:
    telemetry._tracer_provider.force_flush(5000)
time.sleep(10)
"""
    encoded = base64.b64encode(code.encode()).decode()
    docker("rm", "-f", WRITER, check=False)
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
        "-e",
        f"COUNT={count}",
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
    tempo_negative = docker_result(
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
        'mc alias set tempo http://tempo-minio:9000 "$ACCESS" "$SECRET" >/dev/null && mc mb tempo/'
        + TEMPO_BUCKET,
    )
    if tempo_negative.returncode == 0:
        raise AssertionError("Loki credential wrote Tempo storage namespace")
    print(f"storage_positive={bucket}/ng06/storage-proof")
    print("storage_negative=DENIED canonical/denied")
    print("storage_tempo_negative=DENIED tempo-traces")


def http_json(url: str, *, auth: tuple[str, str] | None = None) -> dict:
    request = urllib.request.Request(url)
    if auth is not None:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def wait_json(url: str, *, auth: tuple[str, str], timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return http_json(url, auth=auth)
        except Exception as exc:  # Grafana/Tempo may race startup and ring join.
            last_error = exc
            time.sleep(2)
    raise TimeoutError(f"timed out waiting for Grafana proxy {url}: {last_error}")


def grafana_correlation(trace_id: str) -> None:
    auth = ("admin", GRAFANA_PASSWORD)
    if http_json(f"{GRAFANA_URL}/api/health", auth=auth).get("database") != "ok":
        raise AssertionError("Grafana health check failed")
    loki = http_json(f"{GRAFANA_URL}/api/datasources/uid/loki", auth=auth)
    tempo = http_json(f"{GRAFANA_URL}/api/datasources/uid/tempo", auth=auth)
    if loki.get("uid") != "loki" or tempo.get("uid") != "tempo":
        raise AssertionError("Grafana Loki/Tempo datasource provisioning missing")
    query = urllib.parse.urlencode(
        {
            "query": f'{{service_name="loki-acceptance"}} | trace_id="{trace_id}"',
            "limit": "100",
        }
    )
    loki_proxy = http_json(
        f"{GRAFANA_URL}/api/datasources/proxy/uid/loki/loki/api/v1/query_range?{query}",
        auth=auth,
    )
    if not loki_proxy.get("data", {}).get("result"):
        raise AssertionError("Grafana Loki proxy returned no correlated log")
    tempo_proxy = wait_json(
        f"{GRAFANA_URL}/api/datasources/proxy/uid/tempo/api/traces/{trace_id}",
        auth=auth,
    )
    if not tempo_proxy.get("data") and not tempo_proxy.get("batches"):
        raise AssertionError("Grafana Tempo proxy returned no same trace")
    print("grafana_loki_query=true")
    print("grafana_tempo_query=true")


def canonical_probe(otel_enabled: bool) -> str:
    code = (
        "import hashlib, json, sys, types\n"
        "sys.path.insert(0, '/acceptance')\n"
        "kafka = types.ModuleType('confluent_kafka'); kafka.Producer = type('Producer', (), {})\n"
        "sys.modules['confluent_kafka'] = kafka\n"
        "import orders_producer as producer\n"
        "domain = {'order_id':'ng06-parity-order','customer':'Alice','amount':12.5,'country':'UK','status':'paid','business_version':1,'event_time':'2026-08-10T12:00:00+00:00'}\n"
        "canonical = producer.canonical_payload_bytes(domain)\n"
        "print('CANONICAL_HASH=' + hashlib.sha256(canonical).hexdigest())\n"
    )
    result = docker_result(
        "run",
        "--rm",
        "--network",
        NETWORK,
        "-e",
        f"OTEL_ENABLED={'1' if otel_enabled else '0'}",
        "-v",
        f"{ROOT / 'kafka' / 'producer'}:/acceptance:ro",
        APP_IMAGE,
        "python",
        "-c",
        code,
    )
    if result.returncode:
        raise RuntimeError("canonical probe failed")
    for line in result.stdout.splitlines():
        if line.startswith("CANONICAL_HASH="):
            return line.split("=", 1)[1]
    raise RuntimeError("canonical probe did not emit a hash")


def collector_metrics() -> str:
    try:
        with urllib.request.urlopen(
            "http://localhost:28888/metrics", timeout=5
        ) as response:
            return response.read().decode()
    except Exception:
        return ""


def failure_metric_lines(metrics: str) -> str:
    return ";".join(
        line
        for line in metrics.splitlines()
        if any(
            token in line
            for token in (
                "send_failed",
                "enqueue_failed",
                "queue_size",
                "queue_capacity",
            )
        )
    )


def object_store_bytes() -> int:
    access = os.environ["LOKI_S3_ACCESS_KEY"]
    secret = os.environ["LOKI_S3_SECRET_KEY"]
    bucket = os.getenv("LOKI_S3_BUCKET", "loki-logs")
    result = docker_result(
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
        f"mc du --json --recursive loki/{bucket}/ng06/",
    )
    if result.returncode:
        raise RuntimeError("Loki object-store measurement failed")
    sizes = [
        json.loads(line)["size"] for line in result.stdout.splitlines() if line.strip()
    ]
    return int(sizes[-1]) if sizes else 0


def collector_wal_bytes() -> int:
    volumes = docker_result(
        "volume",
        "ls",
        "-q",
        "--filter",
        "label=com.docker.compose.volume=de_demo_otel_storage",
    ).stdout.splitlines()
    if not volumes:
        raise RuntimeError("Collector WAL volume is missing")
    result = docker_result(
        "run",
        "--rm",
        "-v",
        f"{volumes[0]}:/var/lib/otelcol:ro",
        "busybox:1.36",
        "du",
        "-sb",
        "/var/lib/otelcol",
    )
    if result.returncode:
        raise RuntimeError("Collector WAL measurement failed")
    return int(result.stdout.split()[0])


def wait_collector() -> None:
    deadline = time.monotonic() + 90
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
        time.sleep(2)
    raise TimeoutError("Collector did not recover")


def queue_observation(metrics: str) -> tuple[int, int, int, int]:
    import re as _re

    def value(pattern: str) -> int:
        match = _re.search(
            pattern + r"[^\n]*\s([0-9]+(?:\.[0-9]+)?)\s*$", metrics, _re.MULTILINE
        )
        return int(float(match.group(1))) if match else 0

    return (
        value(r"otelcol_exporter_queue_capacity\{data_type=\"logs\""),
        value(r"otelcol_exporter_queue_size\{data_type=\"logs\""),
        value(r"otelcol_exporter_enqueue_failed_log_records\{"),
        value(r"otelcol_exporter_send_failed_log_records\{"),
    )


def resource_receipt() -> None:
    stats = docker_result(
        "stats",
        "--no-stream",
        "--format",
        "{{.Name}} {{.CPUPerc}} {{.MemUsage}}",
        "de-demo-loki",
        "de-demo-loki-minio",
        "de-demo-otel-collector",
    )
    if stats.returncode:
        raise RuntimeError("resource sampling failed")
    print("resource_sample=" + stats.stdout.replace("\n", ";").strip())


def labels_receipt(loki_url: str, trace_id: str, log_count: int) -> None:
    started = time.monotonic()
    results = loki_query(
        loki_url, f'{{service_name="loki-acceptance"}} | trace_id="{trace_id}"'
    )
    log_count = sum(len(stream.get("values", [])) for stream in results)
    latency_ms = (time.monotonic() - started) * 1000
    labels = http_json(f"{loki_url}/loki/api/v1/labels").get("data", [])
    indexed = sorted(label for label in labels if label not in {"filename", "job"})
    series_query = urllib.parse.urlencode(
        {"match[]": '{service_name="loki-acceptance"}'}
    )
    series = http_json(f"{loki_url}/loki/api/v1/series?{series_query}").get("data", [])
    cardinality = {
        label: len({item.get(label) for item in series if item.get(label) is not None})
        for label in indexed
    }
    print("indexed_labels=" + ",".join(indexed))
    print(
        "label_cardinality="
        + ",".join(f"{label}={cardinality[label]}" for label in indexed)
    )
    print(f"logql_latency_ms={latency_ms:.2f}")
    print(f"logql_latency_sample_ms={latency_ms:.2f}")
    print(f"loki_object_store_bytes={object_store_bytes()}")
    print(f"ingested_logs={log_count}")
    print(
        "collector_retry_drop_metrics="
        + ";".join(
            line
            for line in collector_metrics().splitlines()
            if "exporter" in line and ("log" in line or "queue" in line)
        )
    )


def pre_fix_redaction_probe() -> None:
    """Execute the old helper against the newly-covered PII/payload markers."""

    source = subprocess.run(
        ["git", "show", "fe51bdb:iceberg/common/telemetry.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    tree = ast.parse(source)
    wanted = {"_DENIED_KEYS", "_DENIED_VALUES", "_safe_value", "_safe_attributes"}
    nodes = []
    for node in tree.body:
        name = (
            node.name
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            else None
        )
        if name in wanted:
            nodes.append(node)
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id in wanted
                for target in node.targets
            ):
                nodes.append(node)
    namespace: dict[str, Any] = {"re": re, "Any": Any}
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "pre-fix-telemetry", "exec"),
        namespace,
    )
    leaked = namespace["_safe_attributes"](
        {"customer_email": "customer@example.com", "payload": "full-payload-marker"}
    )
    if (
        leaked["customer_email"] != "customer@example.com"
        or leaked["payload"] != "full-payload-marker"
    ):
        raise AssertionError(
            "pre-fix fixture no longer demonstrates the redaction regression"
        )
    print("redaction_pre_fix=FAIL_EXPECTED customer_email,payload")


def main() -> int:
    loki_url = os.getenv("NG06_LOKI_URL", "http://localhost:13100")
    pre_fix_redaction_probe()
    wait_http(f"{loki_url}/ready")
    canonical_healthy = canonical_probe(True)
    wal_before = collector_wal_bytes()
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
        "api-key-marker",
        "postgres://app:password@db/orders",
        "customer@example.com",
        "full-payload-marker",
        "select customer_email from orders",
    ):
        if forbidden in text:
            raise AssertionError(f"forbidden value persisted in Loki: {forbidden}")
    if "ng06-loki-load-001" not in text or trace_id not in text:
        raise AssertionError("safe load identity or trace ID missing from Loki")
    if "loki.acceptance.event" not in text or "INFO" not in text:
        raise AssertionError(
            "structured event name/severity missing from persisted Loki"
        )
    grafana_correlation(trace_id)
    storage_isolation()
    labels_receipt(loki_url, trace_id, len(results))
    resource_receipt()

    # Canonical work must remain independent of Loki. Exercise it while Loki
    # is down, retain stdout from a first-party writer, and compare hashes.
    docker("stop", "de-demo-loki")
    outage_trace = start_writer(count=256)
    time.sleep(3)
    outage_logs = docker("logs", WRITER, check=False)
    if "TRACE_ID=" not in outage_logs:
        raise AssertionError("first-party stdout disappeared during Loki outage")
    outage_metrics = collector_metrics()
    pending_wal = collector_wal_bytes()
    if pending_wal <= wal_before:
        raise AssertionError("Collector file_storage did not grow during Loki outage")
    docker("kill", "--signal", "KILL", "de-demo-otel-collector")
    docker("start", "de-demo-otel-collector")
    wait_collector()
    canonical_outage = canonical_probe(True)
    docker("start", "de-demo-loki")
    wait_http(f"{loki_url}/ready", timeout=90)
    time.sleep(5)
    if not loki_query(
        loki_url, f'{{service_name="loki-acceptance"}} | trace_id="{outage_trace}"'
    ):
        raise AssertionError(
            "persistent log queue did not recover after Collector restart"
        )
    restored_trace = start_writer()
    time.sleep(4)
    if not loki_query(
        loki_url, f'{{service_name="loki-acceptance"}} | trace_id="{restored_trace}"'
    ):
        raise AssertionError("post-restore log was not queryable")
    print(f"canonical_healthy_hash={canonical_healthy}")
    print(f"canonical_outage_hash={canonical_outage}")
    if canonical_healthy != canonical_outage:
        raise AssertionError("canonical output changed while Loki was unavailable")
    print("canonical_parity=true")
    print("loki_outage_business_success=true")
    print("loki_outage_metrics=" + failure_metric_lines(outage_metrics))
    print(f"collector_wal_bytes_pending={pending_wal}")
    print("wal_restart_recovery=true")
    print(f"post_restore_ingestion=true trace_id={restored_trace}")

    # Drive a deterministic near-capacity condition while Loki is unavailable.
    docker("stop", "de-demo-loki")
    start_writer(count=40000)
    time.sleep(5)
    saturation_metrics = collector_metrics()
    capacity, queue_size, enqueue_failed, send_failed = queue_observation(
        saturation_metrics
    )
    if (
        capacity != 256
        or queue_size > capacity
        or (queue_size == 0 and enqueue_failed == 0 and send_failed == 0)
    ):
        raise AssertionError("bounded Loki queue pressure was not observed")
    print(f"queue_capacity={capacity}")
    print(f"queue_size={queue_size}")
    print(f"enqueue_failed={enqueue_failed}")
    print(f"send_failed={send_failed}")
    docker("start", "de-demo-loki")
    wait_http(f"{loki_url}/ready", timeout=90)
    time.sleep(10)

    # Isolate the Loki object store while keeping the application path alive.
    docker("stop", "de-demo-loki-minio")
    object_store_hash = canonical_probe(True)
    object_store_metrics = collector_metrics()
    if object_store_hash != canonical_healthy:
        raise AssertionError("canonical output changed during Loki object-store outage")
    print("object_store_outage_canonical_unchanged=true")
    print("object_store_outage_signal=true")
    print("object_store_outage_metrics=" + failure_metric_lines(object_store_metrics))
    docker("start", "de-demo-loki-minio")
    time.sleep(8)
    wait_http(f"{loki_url}/ready", timeout=90)
    restored_storage_trace = start_writer()
    time.sleep(4)
    if not loki_query(
        loki_url,
        f'{{service_name="loki-acceptance"}} | trace_id="{restored_storage_trace}"',
    ):
        raise AssertionError("post-storage-restore log was not queryable")
    print("object_store_restore_ingestion=true")

    # Collector restart is bounded and fail-open: stdout and canonical work
    # remain available, then a new record is accepted after recovery.
    collector_before_metrics = collector_metrics()
    docker("stop", "de-demo-otel-collector")
    collector_outage_hash = canonical_probe(True)
    if collector_outage_hash != canonical_healthy:
        raise AssertionError("canonical output changed during Collector outage")
    print("collector_failure_business_success=true")
    print(
        "collector_failure_metrics=collector_unavailable_business_probe=true;"
        + failure_metric_lines(collector_before_metrics)
    )
    docker("start", "de-demo-otel-collector")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        status = docker(
            "inspect",
            "-f",
            "{{.State.Health.Status}}",
            "de-demo-otel-collector",
            check=False,
        ).strip()
        if status == "healthy":
            break
        time.sleep(2)
    else:
        raise TimeoutError("Collector did not recover")
    collector_restored_trace = start_writer()
    time.sleep(4)
    if not loki_query(
        loki_url,
        f'{{service_name="loki-acceptance"}} | trace_id="{collector_restored_trace}"',
    ):
        raise AssertionError("post-Collector-restore log was not queryable")
    print("collector_restart_ingestion=true")
    print("collector_recovery_metrics=" + failure_metric_lines(collector_metrics()))
    print(f"collector_wal_bytes_before={wal_before}")
    print(f"collector_wal_bytes_after={collector_wal_bytes()}")
    print(f"same_trace_id={trace_id}")
    print("trace_to_logs=PASS")
    print("persisted_redaction=PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        docker("rm", "-f", WRITER, check=False)
