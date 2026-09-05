import re
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


def _declared_profiles() -> set[str]:
    """Every Compose profile the repository actually declares."""

    found: set[str] = set()
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for service in (doc.get("services") or {}).values():
            if isinstance(service, dict):
                found.update(str(p) for p in service.get("profiles") or [])
    return found


def _documented_profiles() -> set[str]:
    """Profiles named in the README's `Resource profiles` table.

    A profile is written in backticks there; the `default` row is not a profile
    but the absence of one, and is deliberately written without them.
    """

    readme = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(readme) if line.startswith("## Resource profiles")
    )
    end = next(
        (
            i
            for i, line in enumerate(readme[start + 1 :], start + 1)
            if line.startswith("## ")
        ),
        len(readme),
    )
    documented: set[str] = set()
    for line in readme[start:end]:
        if not line.startswith("|"):
            continue
        first_cell = line.split("|")[1]
        documented.update(re.findall(r"`([a-z][a-z0-9-]*)`", first_cell))
    return documented


def test_every_compose_profile_is_documented() -> None:
    """The profile table is a contract, not a convenience.

    `otel` and `observability-next` were declared in Compose and named in the
    README's own instructions while the table listed neither, so a reader could
    not reconstruct the deployment topology from the table they were pointed at.
    """

    declared = _declared_profiles()
    assert declared, "no profiles found in Compose — detector is blind"
    assert _documented_profiles() == declared
