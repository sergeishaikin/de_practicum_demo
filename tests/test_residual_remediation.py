from __future__ import annotations

from pathlib import Path

import pytest

from dags.recovery_contract import parse_duration, validate_retention_contract


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_retention_contract_requires_a_strict_safety_boundary() -> None:
    contract = validate_retention_contract("2h", "1h", "15m")

    assert contract.retention_seconds == 7200
    assert contract.recovery_horizon_seconds == 3600
    assert contract.safety_margin_seconds == 900


def test_retention_contract_rejects_early_snapshot_expiry() -> None:
    with pytest.raises(ValueError, match="FF-10 retention contract violated"):
        validate_retention_contract("75m", "1h", "15m")


def test_retention_equal_to_recovery_horizon_is_not_safe() -> None:
    with pytest.raises(ValueError, match="FF-10 retention contract violated"):
        validate_retention_contract("1h", "1h", "0s")


@pytest.mark.parametrize("value", ["", "1", "-1h", "0m", "one hour"])
def test_duration_parser_rejects_unsupported_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(value)


def test_maintenance_exports_and_enforces_recovery_contract() -> None:
    source = (REPO_ROOT / "dags" / "lakehouse_maintenance.py").read_text(
        encoding="utf-8"
    )

    assert "MAINTENANCE_RECOVERY_HORIZON" in source
    assert "MAINTENANCE_RECOVERY_SAFETY_MARGIN" in source
    assert "RECOVERY_SAFETY_MARGIN" in source
    assert "validate_retention_contract(" in source
    assert "RETENTION_CONTRACT =" in source


def test_streaming_job_has_explicit_dead_letter_and_data_loss_contract() -> None:
    source = (REPO_ROOT / "spark" / "jobs" / "orders_streaming.py").read_text(
        encoding="utf-8"
    )

    assert '"raw_payload"' in source
    assert '"dead_letter_reason"' in source
    assert '"orders-dead-letter"' in source
    assert '"DEAD_LETTER_CHECKPOINT_PATH"' in source
    assert '"RECONCILIATION_OUTPUT_PATH"' in source
    assert '"RECONCILIATION_CHECKPOINT_PATH"' in source
    assert '"KAFKA_FAIL_ON_DATA_LOSS"' in source
    assert '.option("failOnDataLoss", str(KAFKA_FAIL_ON_DATA_LOSS).lower())' in source
    assert '"invalid_json_or_schema"' in source
    assert '"missing_order_id"' in source
    assert '"observed_count"' in source
    assert '"dead_letter_count"' in source
    assert '"min_kafka_offset"' in source
    assert '"max_kafka_offset"' in source
    assert 'batch_id={batch_id}' in source


def test_streaming_compose_defaults_to_loud_offset_loss() -> None:
    source = (REPO_ROOT / "docker-compose.extended.yml").read_text(
        encoding="utf-8"
    )

    assert "KAFKA_FAIL_ON_DATA_LOSS: ${KAFKA_FAIL_ON_DATA_LOSS:-true}" in source
    assert "orders_dead_letter" in source
    assert "orders_reconciliation" in source
