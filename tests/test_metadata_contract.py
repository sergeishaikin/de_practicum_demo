"""Static guards for the opt-in OpenMetadata control plane."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _metadata_compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.metadata.yml").read_text())


def test_metadata_profile_is_opt_in_and_default_compose_is_clean() -> None:
    metadata = _metadata_compose()
    services = metadata["services"]
    assert services
    assert all(
        "metadata" in service.get("profiles", []) for service in services.values()
    )

    # The default graph does not reference the metadata file or services.
    core = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    extended = yaml.safe_load((ROOT / "docker-compose.extended.yml").read_text())
    assert not any(name.startswith("metadata-") for name in core["services"])
    assert not any(name.startswith("metadata-") for name in extended["services"])


def test_metadata_images_are_immutable_where_the_profile_pulls_them() -> None:
    services = _metadata_compose()["services"]
    env = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in (ROOT / ".env.example").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    pinned = {
        "metadata-postgres",
        "metadata-opensearch",
        "metadata-migrate",
        "metadata-server",
        "metadata-ingestion",
        "metadata-bootstrap",
        "metadata-static-ingestion",
        "metadata-ownership",
        "metadata-lineage-topic",
        "metadata-source-reader",
    }
    for name in pinned:
        image = services[name].get("image", "")
        if image.startswith("${"):
            key = image[2:].split(":", 1)[0]
            image = env.get(key, "")
        assert "@sha256:" in image, (name, image)


def test_connector_credentials_are_reader_identities() -> None:
    script = (ROOT / "metadata/scripts/run_ingestion.py").read_text()
    assert '"username": required("METADATA_SOURCE_READER_USER")' in script
    assert '"username": required("METADATA_AIRFLOW_USER")' not in script
    assert "POSTGRES_USER" not in script

    sql = (ROOT / "metadata/create-reader.sql").read_text()
    assert "GRANT SELECT ON ALL TABLES" in sql
    assert "GRANT INSERT" not in sql
    assert "GRANT UPDATE" not in sql
    assert "GRANT DELETE" not in sql


def test_openlineage_transport_and_consumer_are_reproducible() -> None:
    compose = (ROOT / "docker-compose.metadata.yml").read_text()
    assert "OPENLINEAGE__TRANSPORT__CONFIG__BOOTSTRAP.SERVERS" in compose
    assert "OPENLINEAGE__TRANSPORT__CONFIG__BOOTSTRAP_SERVERS" not in compose
    assert "METADATA_LINEAGE_TOPIC" in compose
    assert "retention.ms=${METADATA_LINEAGE_RETENTION_MS" in compose

    script = (ROOT / "metadata/scripts/run_ingestion.py").read_text()
    assert '"consumerGroupName": os.getenv(' in script
    assert '"lineageInformation": {"dbServiceNames": ["lakehouse_trino"]}' in script
    assert "openlineage_container_adapter" in script

    adapter = (ROOT / "metadata/scripts/openlineage_container_adapter.py").read_text()
    assert '"lineageDetails": {' in adapter
    assert '"source": "OpenLineage"' in adapter
    assert "native_edge_exists" in adapter
    assert 'type": "container"' in adapter
    assert "kafka://" not in adapter


def test_metadata_profile_has_live_ci_coverage() -> None:
    workflow = (ROOT / ".github/workflows/ci-metadata.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" in workflow
    assert "docker-compose.metadata.yml" in workflow
    assert "--profile metadata" in workflow
    assert "metadata-bootstrap" in workflow
    assert "run_ingestion.py runtime" in workflow
    assert "/v1/lineage/table/name/" in workflow
    assert "Metadata-only cleanup" in workflow


def test_ownership_mapping_is_repository_controlled_and_aliases_are_stable() -> None:
    mapping = json.loads((ROOT / "metadata/config/ownership.json").read_text())
    assert set(mapping["teams"]) == {"data-platform", "streaming-platform"}
    all_tables = [
        table for team in mapping["teams"].values() for table in team.get("tables", [])
    ]
    assert "lakehouse_trino.iceberg.bronze.orders" in all_tables
    assert "lakehouse_trino.iceberg.silver.orders_clean" in all_tables
    assert "lakehouse_trino.iceberg.gold.orders_daily_metrics" in all_tables
    assert len(all_tables) == len(set(all_tables))


def test_dbt_compatibility_guard_checks_real_artifact_contract() -> None:
    script = (ROOT / "metadata/scripts/assert_dbt_artifacts.py").read_text()
    assert 'version != "1.12.2"' in script
    assert "catalog columns" in script
    assert "manifest lineage dependencies" in script
    assert "dbt test result" in script
