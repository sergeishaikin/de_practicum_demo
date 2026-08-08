from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_prometheus_config_scrapes_all_runtime_sources_and_loads_rules() -> None:
    config = (ROOT / "observability" / "prometheus" / "prometheus.yml").read_text(
        encoding="utf-8"
    )
    assert "rule_files:" in config
    for job in (
        "iceberg-writer",
        "iceberg-medallion",
        "orders-streaming",
        "durable-metrics-exporter",
    ):
        assert f"job_name: {job}" in config


def test_prometheus_rules_are_actionable_and_not_arbitrary() -> None:
    rules = (ROOT / "observability" / "prometheus" / "alerts.yml").read_text(
        encoding="utf-8"
    )
    for alert in (
        "LakehouseUnresolvedWork",
        "LakehouseFF14Conflict",
        "LakehouseShadowMismatch",
        "LakehouseApplicationFailure",
        "LakehouseMaintenanceFailure",
    ):
        assert f"alert: {alert}" in rules
    assert "for: 10m" in rules
    assert "for: 1m" in rules


def test_grafana_dashboard_has_four_required_sections_and_repository_provisioning() -> None:
    dashboard_path = (
        ROOT / "observability" / "grafana" / "dashboards" / "lakehouse-runtime.json"
    )
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    rows = {
        panel["title"]
        for panel in dashboard["panels"]
        if panel.get("type") == "row"
    }
    assert rows == {
        "Pipeline Health",
        "Progress & Recovery",
        "Correctness",
        "Performance",
    }
    assert (
        ROOT / "observability" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    ).exists()
    assert (
        ROOT / "observability" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml"
    ).exists()


def test_compose_declares_prometheus_grafana_and_runtime_healthchecks() -> None:
    compose = (ROOT / "docker-compose.extended.yml").read_text(encoding="utf-8")
    for service in ("observability-exporter:", "prometheus:", "grafana:"):
        assert service in compose
    assert "de_demo_prometheus_data:" in compose
    assert "de_demo_grafana_data:" in compose
    assert "/-/ready" in compose
    assert "/api/health" in compose


def test_runtime_metric_contract_is_exposed_by_application_paths() -> None:
    ops = (ROOT / "iceberg" / "common" / "ops.py").read_text(encoding="utf-8")
    streaming = (ROOT / "spark" / "jobs" / "orders_streaming.py").read_text(
        encoding="utf-8"
    )
    for metric in (
        "lakehouse_events",
        "lakehouse_work",
        "lakehouse_correctness",
        "lakehouse_stage_duration_seconds",
    ):
        assert metric in ops
    for metric in (
        "spark_batches",
        "spark_dead_letter_events",
        "spark_query_up",
    ):
        assert metric in streaming
