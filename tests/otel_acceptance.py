"""Disposable OTLP network acceptance harness for NG-0.4.

The production Collector remains debug-only. This script creates a temporary
source exporter and a second Collector as a test sink on an isolated network.
It exercises delivery, outage/queue pressure, restart/WAL and recovery without
touching application state or adding a product backend.
"""

from __future__ import annotations

import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env.example"
BASE_CONFIG = ROOT / "observability" / "otel" / "collector-config.yaml"
NETWORK = "ng04-otel-acceptance"
SOURCE = "ng04-otel-accept-source"
SINK = "ng04-otel-accept-sink"
APP_IMAGE = "de-practicum-demo-iceberg:0.11.1-h1"


def docker(*args: str, timeout: float = 30, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], cwd=ROOT, text=True, capture_output=True, timeout=timeout
    )
    if check and result.returncode:
        raise RuntimeError(
            f"docker {' '.join(args)} failed ({result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def digest() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("OTEL_COLLECTOR_IMAGE="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("OTEL_COLLECTOR_IMAGE is not pinned")


def source_config() -> str:
    config = BASE_CONFIG.read_text(encoding="utf-8")
    config = config.replace(
        "  debug:\n    verbosity: basic\n",
        """  debug:
    verbosity: basic
  otlp/acceptance:
    endpoint: sink:4317
    tls:
      insecure: true
    retry_on_failure:
      enabled: true
      initial_interval: 200ms
      max_interval: 1s
      max_elapsed_time: 30s
    sending_queue:
      enabled: true
      num_consumers: 1
      queue_size: 4
      storage: file_storage
""",
    )
    # Replace the production trace route in the disposable source collector;
    # this keeps the NG-0.4 harness isolated from the optional Tempo backend.
    config = config.replace(
        "exporters: [debug, otlp_grpc/telemetry-backend]\n",
        "exporters: [debug, otlp/acceptance]\n",
    )
    config = config.replace(
        "exporters: [debug]\n", "exporters: [debug, otlp/acceptance]\n"
    )
    if "otlp/acceptance" not in config:
        raise RuntimeError("acceptance exporter was not inserted")
    return config


def pressure_config() -> str:
    config = source_config()
    config = config.replace("queue_size: 4", "queue_size: 1")
    config = config.replace("max_elapsed_time: 30s", "max_elapsed_time: 2s")
    config = config.replace("max_interval: 5s", "max_interval: 500ms")
    config = config.replace(
        "    send_batch_size: 128", "    send_batch_size: 1\n    send_batch_max_size: 1"
    )
    config = config.replace("      storage: file_storage\n", "")
    return config


def sink_config() -> str:
    return """extensions:
  health_check:
    endpoint: 0.0.0.0:13133
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
processors:
  batch:
    timeout: 100ms
    send_batch_size: 16
exporters:
  debug:
    verbosity: detailed
service:
  telemetry:
    metrics:
      level: basic
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8888
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
"""


def wait_ready(name: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if name == SOURCE:
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:28888/metrics", timeout=1
                ):
                    return
            except Exception:
                pass
        if name == SINK:
            try:
                with urllib.request.urlopen("http://127.0.0.1:24319/", timeout=1):
                    return
            except Exception:
                pass
        logs = docker("logs", name, timeout=10, check=False)
        if "Everything is ready" in logs:
            return
        state = docker(
            "inspect", "-f", "{{.State.Status}}", name, timeout=10, check=False
        )
        if state.strip() == "exited":
            detail = docker(
                "inspect",
                "-f",
                "{{.State.ExitCode}} {{.State.Error}}",
                name,
                timeout=10,
                check=False,
            )
            raise RuntimeError(
                f"{name} exited before readiness ({detail.strip()}):\n{logs}"
            )
        if state.strip() == "running" and time.monotonic() + 25 > deadline:
            # The minimal collector image may use a non-forwarded log driver;
            # a running process after the bounded startup window is the sink's
            # readiness signal. The source additionally requires /metrics.
            return
        time.sleep(0.5)
    logs = docker("logs", name, timeout=10, check=False)
    state = docker("inspect", "-f", "{{.State.Status}}", name, timeout=10, check=False)
    raise TimeoutError(f"{name} did not become ready (state={state.strip()}):\n{logs}")


def start_collector(name: str, config: Path, image: str, volume: str) -> None:
    ports = (
        ("-p", "28888:8888")
        if name == SOURCE
        else ("-p", "24319:13133", "-p", "28889:8888")
    )
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--entrypoint",
        "/otelcol-contrib",
        "--network",
        NETWORK,
        "--network-alias",
        "source" if name == SOURCE else "sink",
        *ports,
        "-v",
        f"{config}:/etc/otelcol-contrib/config.yaml:ro",
        "-v",
        f"{volume}:/var/lib/otelcol",
        image,
        "--config=/etc/otelcol-contrib/config.yaml",
    )


def emit_spans(count: int) -> None:
    code = f"""from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
p = TracerProvider()
p.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint='http://source:4317', insecure=True, timeout=2), max_export_batch_size=8, schedule_delay_millis=50))
trace.set_tracer_provider(p)
t = trace.get_tracer('ng04-otel-acceptance')
for i in range({count}):
    with t.start_as_current_span('accept.normal', attributes={{'accept.index': i}}):
        pass
p.force_flush(5000)
p.shutdown()
"""
    docker(
        "run",
        "--rm",
        "--network",
        NETWORK,
        APP_IMAGE,
        "python",
        "-c",
        code,
        timeout=30,
    )


def canonical_probe(otel_enabled: bool) -> str:
    code = (
        "import hashlib, json, os, sys, types\n"
        "sys.path.insert(0, '/acceptance')\n"
        "kafka = types.ModuleType('confluent_kafka')\n"
        "kafka.Producer = type('Producer', (), {})\n"
        "sys.modules['confluent_kafka'] = kafka\n"
        "import orders_producer as producer\n"
        "domain = {'order_id':'m2c-order','customer':'Alice','amount':12.5,'country':'UK','status':'paid','business_version':1,'event_time':'2026-08-10T12:00:00+00:00'}\n"
        "if os.environ.get('OTEL_ENABLED') == '1':\n"
        "    from opentelemetry import trace\n"
        "    from opentelemetry.sdk.trace import TracerProvider\n"
        "    from opentelemetry.sdk.trace.export import BatchSpanProcessor\n"
        "    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter\n"
        "    provider = TracerProvider()\n"
        "    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint='http://source:4317', insecure=True, timeout=1), schedule_delay_millis=50))\n"
        "    trace.set_tracer_provider(provider)\n"
        "    with trace.get_tracer('m2c').start_as_current_span('canonical-probe'): pass\n"
        "    provider.force_flush(1500)\n"
        "    provider.shutdown()\n"
        "canonical = producer.canonical_payload_bytes(domain)\n"
        "print('CANONICAL_HASH=' + hashlib.sha256(canonical).hexdigest())\n"
    )
    output = docker(
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
        timeout=20,
    )
    for line in output.splitlines():
        if line.startswith("CANONICAL_HASH="):
            return line.split("=", 1)[1]
    raise RuntimeError(f"canonical probe did not emit a hash: {output}")


def collector_metrics() -> str:
    with urllib.request.urlopen(
        "http://127.0.0.1:28888/metrics", timeout=3
    ) as response:
        return response.read().decode("utf-8")


def sink_metrics() -> str:
    with urllib.request.urlopen(
        "http://127.0.0.1:28889/metrics", timeout=3
    ) as response:
        return response.read().decode("utf-8")


def metric_value(text: str, metric: str) -> int:
    for line in text.splitlines():
        if line.startswith(metric + " "):
            return int(float(line.rsplit(" ", 1)[1]))
    return 0


def wait_metric(
    url: str, metric: str, minimum: int, timeout: float = 10
) -> tuple[int, str]:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        with urllib.request.urlopen(url, timeout=3) as response:
            latest = response.read().decode("utf-8")
        value = metric_value(latest, metric)
        if value >= minimum:
            return value, latest
        time.sleep(0.5)
    return metric_value(latest, metric), latest


def metric_excerpt(text: str) -> str:
    needles = (
        "queue",
        "send_failed",
        "enqueue_failed",
        "dropped",
        "sent_spans",
        "accepted_spans",
        "refused_spans",
    )
    return "\n".join(
        line
        for line in text.splitlines()
        if line.startswith("otelcol_") and any(needle in line for needle in needles)
    )


def positive_drop_metrics(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if any(token in line for token in ("enqueue_failed", "dropped")):
            try:
                if float(line.rsplit(" ", 1)[1]) > 0:
                    lines.append(line)
            except (IndexError, ValueError):
                continue
    return "\n".join(lines)


def container_stats() -> str:
    return docker(
        "stats",
        "--no-stream",
        "--format",
        "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}",
        SOURCE,
        SINK,
        timeout=20,
        check=False,
    ).strip()


def wal_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    image = digest()
    with tempfile.TemporaryDirectory(prefix="ng04-otel-accept-") as temp:
        path = Path(temp)
        source_path = path / "source.yaml"
        sink_path = path / "sink.yaml"
        source_path.write_text(source_config(), encoding="utf-8")
        sink_path.write_text(sink_config(), encoding="utf-8")
        try:
            docker(
                "run",
                "--rm",
                "-v",
                f"{source_path}:/etc/otelcol-contrib/config.yaml:ro",
                image,
                "validate",
                "--config=/etc/otelcol-contrib/config.yaml",
                timeout=30,
            )
            docker(
                "run",
                "--rm",
                "-v",
                f"{sink_path}:/etc/otelcol-contrib/config.yaml:ro",
                image,
                "validate",
                "--config=/etc/otelcol-contrib/config.yaml",
                timeout=30,
            )
            docker("network", "create", NETWORK, timeout=20)
            baseline_stats = container_stats()
            source_wal = path / "source-wal"
            sink_wal = path / "sink-wal"
            source_wal.mkdir()
            sink_wal.mkdir()
            start_collector(SOURCE, source_path, image, str(source_wal))
            wait_ready(SOURCE)
            before = metric_excerpt(collector_metrics())

            # Normal delivery to the disposable OTLP sink.
            start_collector(SINK, sink_path, image, str(sink_wal))
            wait_ready(SINK)
            emit_spans(8)
            normal_received, normal_sink_metrics = wait_metric(
                "http://127.0.0.1:28889/metrics",
                'otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"}',
                8,
            )

            # Sink outage fills the bounded queue; restart source, then recover.
            docker("stop", SINK, timeout=20)
            emit_spans(64)
            outage = metric_excerpt(collector_metrics())
            docker("restart", SOURCE, timeout=30)
            wait_ready(SOURCE)
            docker("rm", "-f", SINK, timeout=20, check=False)
            start_collector(SINK, sink_path, image, str(sink_wal))
            wait_ready(SINK)
            emit_spans(2)
            time.sleep(2)
            recovered = metric_excerpt(collector_metrics())
            recovered_received, recovered_sink_metrics = wait_metric(
                "http://127.0.0.1:28889/metrics",
                'otelcol_receiver_accepted_spans{receiver="otlp",transport="grpc"}',
                2,
            )

            canonical_off = canonical_probe(False)
            canonical_on = canonical_probe(True)
            docker("stop", SINK, timeout=20)
            canonical_outage = canonical_probe(True)

            # Finite queue/drop mode: use a separate temporary config with no
            # WAL storage, queue_size=1 and a 2-second retry horizon. The sink
            # remains absent so enqueue/send failure metrics must surface.
            docker("rm", "-f", SINK, timeout=20, check=False)
            docker("rm", "-f", SOURCE, timeout=20, check=False)
            pressure_path = path / "pressure.yaml"
            pressure_wal = path / "pressure-wal"
            pressure_wal.mkdir()
            pressure_path.write_text(pressure_config(), encoding="utf-8")
            docker(
                "run",
                "--rm",
                "-v",
                f"{pressure_path}:/etc/otelcol-contrib/config.yaml:ro",
                image,
                "validate",
                "--config=/etc/otelcol-contrib/config.yaml",
                timeout=30,
            )
            start_collector(SOURCE, pressure_path, image, str(pressure_wal))
            wait_ready(SOURCE)
            emit_spans(128)
            time.sleep(4)
            pressure_metrics = metric_excerpt(collector_metrics())
            pressure_drops = positive_drop_metrics(collector_metrics())

            print(f"normal_received_spans={normal_received}")
            print(f"recovered_received_spans={recovered_received}")
            print(f"metrics_before=\n{before or '<none>'}")
            print(f"metrics_outage=\n{outage or '<none>'}")
            print(f"metrics_recovered=\n{recovered or '<none>'}")
            print(f"sink_metrics_normal=\n{normal_sink_metrics}")
            print(f"sink_metrics_recovered=\n{recovered_sink_metrics}")
            print(f"pressure_metrics=\n{pressure_metrics or '<none>'}")
            print(f"pressure_drop_metrics=\n{pressure_drops or '<none>'}")
            print(f"canonical_off={canonical_off}")
            print(f"canonical_on={canonical_on}")
            print(f"canonical_outage={canonical_outage}")
            print(f"container_stats=\n{container_stats()}")
            print(
                f"baseline_container_stats=\n{baseline_stats or '<no Collector containers>'}"
            )
            print(f"source_wal_bytes={wal_bytes(source_wal)}")
            if normal_received < 8:
                raise AssertionError("normal OTLP delivery did not reach sink")
            if recovered_received <= 0:
                raise AssertionError("recovery drain did not reach sink")
            if not pressure_drops:
                raise AssertionError(
                    "finite queue did not expose a positive drop metric"
                )
            if not (canonical_off == canonical_on == canonical_outage):
                raise AssertionError("canonical output changed across telemetry modes")
            return 0
        finally:
            for name in (SINK, SOURCE):
                docker("rm", "-f", name, timeout=20, check=False)
            docker("network", "rm", NETWORK, timeout=20, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
