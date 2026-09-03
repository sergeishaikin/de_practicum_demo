from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_tempo_profile_is_optional_and_pinned() -> None:
    compose = _read("docker-compose.extended.yml")
    env = _read(".env.example")
    config = _read("observability/tempo/tempo.yaml")

    assert 'profiles: ["observability-next"]' in compose
    assert "TEMPO_IMAGE=grafana/tempo@sha256:" in env
    assert "TEMPO_MINIO_IMAGE=minio/minio@sha256:" in env
    assert "TEMPO_MINIO_MC_IMAGE=minio/mc@sha256:" in env
    assert "target: all" in config
    assert "backend: s3" in config
    assert "block_retention: 24h" in config
    assert "compaction_window: 1h" in config
    assert "metrics_generator:" not in config
    assert "spanmetrics" not in config


def test_tempo_storage_isolated_from_canonical_minio() -> None:
    compose = _read("docker-compose.extended.yml")
    config = _read("observability/tempo/tempo.yaml")

    assert "tempo-minio:" in compose
    assert "de_demo_tempo_minio_data:" in compose
    assert "de_demo_tempo_data:" in compose
    assert "TEMPO_S3_ACCESS_KEY" in compose
    assert "MINIO_ROOT_USER: ${MINIO_ROOT_USER}" in compose
    assert "bucket: ${TEMPO_S3_BUCKET}" in config
    assert "prefix: ${TEMPO_S3_PREFIX}" in config
    assert "TEMPO_S3_ENDPOINT: tempo-minio:9000" in compose
    assert "de-practicum/warehouse" not in config


def test_collector_route_stays_at_telemetry_backend_boundary() -> None:
    config = _read("observability/otel/collector-config.yaml")

    assert "otlp_grpc/telemetry-backend:" in config
    assert "endpoint: tempo:4317" in config
    assert "sending_queue:" in config
    assert "retry_on_failure:" in config
    assert "exporters: [debug, otlp_grpc/telemetry-backend]" in config
    assert "kafka" not in config.lower()


def test_grafana_and_prometheus_correlation_uids_are_deterministic() -> None:
    prometheus = _read("observability/grafana/provisioning/datasources/prometheus.yml")
    tempo = _read("observability/grafana/provisioning/datasources/tempo.yml")

    assert "uid: prometheus" in prometheus
    assert "exemplarTraceIdDestinations:" in prometheus
    assert "datasourceUid: tempo" in prometheus
    assert "uid: tempo" in tempo
    assert "url: http://tempo:3200" in tempo
    assert "tracesToMetrics:" in tempo
    assert "datasourceUid: prometheus" in tempo
    assert "lakehouse_duration_seconds_count" in tempo
    assert "tracesToLogsV2" not in tempo


def test_tempo_does_not_change_application_otlp_destination() -> None:
    env = _read(".env.example")
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317" in env
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo" not in env
