from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_collector_contract_is_opt_in_and_bounded() -> None:
    compose = (ROOT / "docker-compose.extended.yml").read_text(encoding="utf-8")
    config = (ROOT / "observability" / "otel" / "collector-config.yaml").read_text(
        encoding="utf-8"
    )
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert 'profiles: ["otel"]' in compose
    assert "otel-collector:4317" in compose
    assert "4318" not in config
    assert "file_storage" in config
    assert "create_directory: true" in config
    assert "memory_limiter" in config
    assert "without_type_suffix: true" in config
    assert "OTEL_COLLECTOR_IMAGE=ghcr.io/open-telemetry" in env
    assert (
        "@sha256:f2f01157055a9b2aab9df7118e1f1c9abf345e99b23bc7a2bc791db374a7d0f6"
        in env
    )


def test_span_metrics_and_direct_backend_paths_are_locked_out() -> None:
    design = (
        ROOT / "openspec/changes/add-opentelemetry-collector/design.md"
    ).read_text(encoding="utf-8")
    assert "spanmetrics" in design
    assert "telemetry-backend" in design
    assert "no per-service Tempo/Loki/vendor" in design


@pytest.mark.skipif(
    importlib.util.find_spec("opentelemetry") is None,
    reason="OTel SDK is installed in service images, not the root test environment",
)
def test_kafka_trace_context_round_trip() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "kafka" / "producer"))
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        from propagation import extract_context, inject_headers

        trace.set_tracer_provider(TracerProvider())
        tracer = trace.get_tracer("contract-test")
        with tracer.start_as_current_span("producer"):
            headers = inject_headers([("x-test", b"ok")])
        context = extract_context(headers)
        assert context is not None
        assert any(key == "traceparent" for key, _ in headers)
    finally:
        sys.path.pop(0)
