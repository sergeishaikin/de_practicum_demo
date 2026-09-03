from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _compose(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_optional_services_have_one_resource_profile() -> None:
    services = _compose("docker-compose.extended.yml")["services"]
    expected = {
        "spark-connect": ["tools"],
        "jupyter": ["tools"],
        "kafka-ui": ["tools"],
        "metabase": ["bi"],
        "superset": ["bi"],
        "superset-mcp": ["bi"],
        "observability-exporter": ["observability"],
        "prometheus": ["observability"],
        "grafana": ["observability"],
    }

    assert {name: services[name]["profiles"] for name in expected} == expected


def test_every_runtime_service_has_a_memory_limit() -> None:
    base = _compose("docker-compose.yml")["services"]
    local = _compose("docker-compose.local-airflow.yml")["services"]
    extended = _compose("docker-compose.extended.yml")["services"]
    metadata = _compose("docker-compose.metadata.yml")["services"]

    assert all("mem_limit" in service for service in base.values())
    assert all("mem_limit" in service for service in local.values())
    assert all("mem_limit" in service for service in extended.values())

    inherited_overrides = {"de-demo-airflow", "iceberg-writer", "iceberg-medallion"}
    assert all(
        "mem_limit" in service
        for name, service in metadata.items()
        if name not in inherited_overrides
    )


def test_base_and_offline_airflow_use_the_same_limits() -> None:
    base = _compose("docker-compose.yml")["services"]
    local = _compose("docker-compose.local-airflow.yml")["services"]

    for name in ("de-demo-postgres", "airflow-db-init", "de-demo-airflow"):
        assert local[name]["mem_limit"] == base[name]["mem_limit"]


def test_jvm_and_spark_capacity_stay_below_container_limits() -> None:
    extended = _compose("docker-compose.extended.yml")["services"]

    assert extended["spark-worker"]["environment"]["SPARK_WORKER_MEMORY"] == "2g"
    assert extended["kafka"]["environment"]["KAFKA_HEAP_OPTS"] == ("-Xms256m -Xmx512m")
    assert extended["iceberg-rest"]["environment"]["JAVA_TOOL_OPTIONS"] == (
        "-Xms128m -Xmx384m"
    )
    assert (ROOT / "trino/etc/jvm.config").read_text(encoding="utf-8").splitlines()[
        1
    ] == "-Xmx1G"
