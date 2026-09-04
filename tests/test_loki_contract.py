from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_loki_profile_is_pinned_and_isolated() -> None:
    compose = _read("docker-compose.extended.yml")
    env = _read(".env.example")
    config = _read("observability/loki/loki.yaml")
    assert 'profiles: ["observability-next"]' in compose
    assert "loki-minio:" in compose
    assert "de_demo_loki_minio_data" in compose
    assert "de_demo_loki_data" in compose
    assert (
        "LOKI_IMAGE=grafana/loki@sha256:d70e4659623f3e109af669cae76fe2a5dd5be54e2298fe8aed380d982fbc2500"
        in env
    )
    assert "schema: v13" in config
    assert "store: tsdb" in config
    assert "period: 24h" in config
    assert "allow_structured_metadata: true" in config
    assert "retention_enabled: true" in config
    assert "retention_period: 48h" in config
    assert "delete_request_store: s3" in config


def test_loki_otlp_route_and_explicit_label_allow_list() -> None:
    collector = _read("observability/otel/collector-config.yaml")
    config = _read("observability/loki/loki.yaml")
    assert "otlphttp/loki:" in collector
    assert "endpoint: http://loki:3100/otlp" in collector
    assert "exporters: [debug, otlphttp/loki]" in collector
    assert "default_resource_attributes_as_index_labels" in config
    assert "service.name" in config
    assert "service.namespace" in config
    assert "deployment.environment.name" in config
    assert "service.instance.id" not in config
    assert "service.instance.id" not in config
    assert (
        "trace_id"
        not in config.split("default_resource_attributes_as_index_labels", 1)[1]
    )


def test_grafana_trace_to_logs_uses_structured_metadata_label() -> None:
    loki = _read("observability/grafana/provisioning/datasources/loki.yml")
    tempo = _read("observability/grafana/provisioning/datasources/tempo.yml")
    assert "uid: loki" in loki
    assert "matcherType: label" in loki
    assert "matcherRegex: ^trace[_]?id$" in loki
    assert "datasourceUid: tempo" in loki
    assert "tracesToLogsV2:" in tempo
    assert "datasourceUid: loki" in tempo
    assert "value: service_name" in tempo
    assert "value: service_namespace" in tempo


def test_loki_does_not_replace_existing_metric_authority() -> None:
    collector = _read("observability/otel/collector-config.yaml")
    assert "otlp_grpc/telemetry-backend" in collector
    assert "prometheus:" in collector
    assert "telemetry-backend" in collector


def test_first_party_logging_boundary_requires_structured_identity() -> None:
    telemetry = _read("iceberg/common/telemetry.py")
    assert "event_name: str" in telemetry
    assert 'severity: str = "INFO"' in telemetry
    assert '"event.name"' in telemetry
    assert '"severity"' in telemetry
    for marker in ("customer[_-]?email", "payload", "@[^\\s,;]+"):
        assert marker in telemetry


def test_first_party_scope_is_truthful_about_unadapted_surfaces() -> None:
    design = _read("openspec/changes/add-loki-log-backend/design.md")
    assert "out of" in design.lower() and "first adopted wave" in design.lower()
    assert "Kafka producer" in design
    assert "Spark streaming jobs" in design
    assert "Airflow DAG code" in design


def test_loki_queue_uses_persistent_collector_storage() -> None:
    collector = _read("observability/otel/collector-config.yaml")
    loki_block = collector.split("otlphttp/loki:", 1)[1].split("service:", 1)[0]
    assert "sending_queue:" in loki_block
    assert "storage: file_storage" in loki_block
