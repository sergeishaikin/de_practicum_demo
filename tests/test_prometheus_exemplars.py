from __future__ import annotations

import sys
import types

import prometheus_client

from common import ops, telemetry


def _runtime(monkeypatch):
    served: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(
        prometheus_client,
        "start_http_server",
        lambda *args, **kwargs: served.append((args, kwargs)),
    )
    return ops._RuntimeMetrics("9099")


def _observation() -> dict[str, int | str]:
    return {
        "source": "writer",
        "status": "success",
        "rows_processed": 1,
        "files_processed": 1,
        "duration_ms": 1250,
        "work_available": 1,
        "work_in_flight": 0,
        "work_completed": 1,
        "keys_processed": 1,
        "lower_versions_ignored": 0,
        "ff14_conflicts": 0,
        "shadow_mismatches": 0,
        "silver_duration_ms": 0,
        "gold_duration_ms": 0,
        "files_planned": 1,
        "files_removed": 0,
        "files_added": 1,
        "bytes_planned": 100,
        "bytes_removed": 0,
        "bytes_added": 100,
    }


def test_sampled_trace_context_maps_to_canonical_lowercase_trace_id(
    monkeypatch,
) -> None:
    class Flags:
        sampled = True

    class Context:
        is_valid = True
        trace_id = int("0123456789abcdef" * 2, 16)
        trace_flags = Flags()

    trace_module = types.ModuleType("opentelemetry.trace")
    trace_module.get_current_span = lambda: types.SimpleNamespace(
        get_span_context=lambda: Context()
    )
    otel_module = types.ModuleType("opentelemetry")
    otel_module.trace = trace_module
    monkeypatch.setitem(sys.modules, "opentelemetry", otel_module)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_module)
    monkeypatch.setenv("OTEL_ENABLED", "1")

    assert telemetry.current_trace_exemplar() == {
        "trace_id": "0123456789abcdef0123456789abcdef"
    }


def test_unsampled_trace_context_is_not_used_as_an_exemplar(monkeypatch) -> None:
    class Flags:
        sampled = False

    class Context:
        is_valid = True
        trace_id = 1
        trace_flags = Flags()

    trace_module = types.ModuleType("opentelemetry.trace")
    trace_module.get_current_span = lambda: types.SimpleNamespace(
        get_span_context=lambda: Context()
    )
    otel_module = types.ModuleType("opentelemetry")
    otel_module.trace = trace_module
    monkeypatch.setitem(sys.modules, "opentelemetry", otel_module)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_module)
    monkeypatch.setenv("OTEL_ENABLED", "1")

    assert telemetry.current_trace_exemplar() is None


def test_untraced_observation_has_no_exemplar_and_no_trace_label(
    monkeypatch,
) -> None:
    runtime = _runtime(monkeypatch)
    monkeypatch.setattr(ops, "current_trace_exemplar", lambda: None)

    runtime.observe(**_observation())

    samples = [
        sample for metric in runtime.duration.collect() for sample in metric.samples
    ]
    assert all(sample.exemplar is None for sample in samples)
    assert "trace_id" not in runtime.duration._labelnames
    assert all("trace_id" not in sample.labels for sample in samples)


def test_sampled_observation_exposes_openmetrics_exemplar_without_new_series(
    monkeypatch,
) -> None:
    runtime = _runtime(monkeypatch)
    trace_id = "fedcba9876543210fedcba9876543210"
    monkeypatch.setattr(ops, "current_trace_exemplar", lambda: {"trace_id": trace_id})

    runtime.observe(**_observation())

    samples = [
        sample for metric in runtime.duration.collect() for sample in metric.samples
    ]
    exemplar_samples = [sample for sample in samples if sample.exemplar is not None]
    assert len(exemplar_samples) == 1
    assert exemplar_samples[0].exemplar.labels == {"trace_id": trace_id}
    assert "trace_id" not in runtime.duration._labelnames
    assert '# {trace_id="fedcba9876543210fedcba9876543210"}' in (
        prometheus_client.openmetrics.exposition.generate_latest(
            runtime.registry
        ).decode()
    )


def test_invalid_exemplar_falls_back_to_the_authoritative_observation(
    monkeypatch,
) -> None:
    runtime = _runtime(monkeypatch)
    monkeypatch.setattr(ops, "current_trace_exemplar", lambda: {"bad label": "x"})

    runtime.observe(**_observation())

    assert any(
        sample.name == "lakehouse_duration_seconds_count" and sample.value == 1
        for metric in runtime.duration.collect()
        for sample in metric.samples
    )
