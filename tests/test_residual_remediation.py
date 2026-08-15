from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from dags.recovery_contract import parse_duration, validate_retention_contract


REPO_ROOT = Path(__file__).resolve().parents[1]
STREAMING_JOB_PATH = REPO_ROOT / "spark" / "jobs" / "orders_streaming.py"


def _load_streaming_job(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
):
    """Import the job without requiring Spark or connecting to external services."""

    for name in (
        "SOURCE_EPOCH_ID",
        "NEW_BASELINE_CHECKPOINT_ROOT",
        "DEAD_LETTER_CHECKPOINT_PATH",
        "RECONCILIATION_CHECKPOINT_PATH",
        "NEW_BASELINE_DEAD_LETTER_CHECKPOINT_PATH",
        "NEW_BASELINE_RECONCILIATION_CHECKPOINT_PATH",
        "B2_NEW_BASELINE_DEAD_LETTER_CHECKPOINT_PATH",
        "B2_NEW_BASELINE_RECONCILIATION_CHECKPOINT_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    class Stub:
        def __init__(self, *_args, **_kwargs):
            pass

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = Stub
    prometheus_stub.Gauge = Stub
    prometheus_stub.start_http_server = lambda *_args, **_kwargs: None

    pyspark_stub = types.ModuleType("pyspark")
    sql_stub = types.ModuleType("pyspark.sql")
    functions_stub = types.ModuleType("pyspark.sql.functions")
    types_stub = types.ModuleType("pyspark.sql.types")
    sql_stub.DataFrame = Stub
    sql_stub.SparkSession = Stub
    sql_stub.functions = functions_stub
    for type_name in (
        "DoubleType",
        "LongType",
        "StringType",
        "StructField",
        "StructType",
        "TimestampType",
    ):
        setattr(types_stub, type_name, Stub)

    monkeypatch.setitem(sys.modules, "psycopg2", types.ModuleType("psycopg2"))
    monkeypatch.setitem(sys.modules, "prometheus_client", prometheus_stub)
    monkeypatch.setitem(sys.modules, "pyspark", pyspark_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql", sql_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.types", types_stub)

    spec = importlib.util.spec_from_file_location(
        "_test_orders_streaming_config", STREAMING_JOB_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_maintenance_uses_compatible_non_retried_expiry() -> None:
    source = (REPO_ROOT / "dags" / "lakehouse_maintenance.py").read_text(
        encoding="utf-8"
    )

    assert "clean_expired_metadata => false" in source
    assert "clean_expired_metadata => true" not in source
    assert '"retries": 0' in source
    assert "retry" not in source.lower()


def test_each_mapped_maintenance_task_owns_failure_audit() -> None:
    source = (REPO_ROOT / "dags" / "lakehouse_maintenance.py").read_text(
        encoding="utf-8"
    )

    assert "max_active_tis_per_dagrun=1" in source
    assert 'f"failed:{operation}"' in source
    assert "on conflict (run_id, table_name) do update" in source
    assert "raise\n" in source
    assert "def capture_before" not in source
    assert "def write_audit" not in source


def test_streaming_job_has_explicit_dead_letter_and_data_loss_contract() -> None:
    source = STREAMING_JOB_PATH.read_text(encoding="utf-8")

    assert '"raw_payload"' in source
    assert '"dead_letter_reason"' in source
    assert '"orders-dead-letter"' in source
    assert '"RECONCILIATION_OUTPUT_PATH"' in source
    assert '"KAFKA_FAIL_ON_DATA_LOSS"' in source
    assert '.option("failOnDataLoss", str(KAFKA_FAIL_ON_DATA_LOSS).lower())' in source
    assert '"invalid_json_or_schema"' in source
    assert '"missing_order_id"' in source
    assert '"observed_count"' in source
    assert '"dead_letter_count"' in source
    assert '"min_kafka_offset"' in source
    assert '"max_kafka_offset"' in source
    assert "batch_id={batch_id}" in source


@pytest.mark.parametrize(
    ("environment", "expected_dead_letter", "expected_reconciliation"),
    [
        (
            {
                "DEAD_LETTER_CHECKPOINT_PATH": "s3a://custom/legacy-dlq",
                "RECONCILIATION_CHECKPOINT_PATH": "s3a://custom/legacy-reconciliation",
            },
            "s3a://custom/legacy-dlq",
            "s3a://custom/legacy-reconciliation",
        ),
        (
            {
                "SOURCE_EPOCH_ID": "epoch-42",
                "NEW_BASELINE_DEAD_LETTER_CHECKPOINT_PATH": "s3a://custom/new-dlq",
                "NEW_BASELINE_RECONCILIATION_CHECKPOINT_PATH": "s3a://custom/new-reconciliation",
            },
            "s3a://custom/new-dlq",
            "s3a://custom/new-reconciliation",
        ),
        (
            {
                "SOURCE_EPOCH_ID": "epoch-42",
                "NEW_BASELINE_CHECKPOINT_ROOT": "s3a://custom/checkpoints/",
            },
            "s3a://custom/checkpoints/epoch-42/dead_letter",
            "s3a://custom/checkpoints/epoch-42/reconciliation",
        ),
    ],
)
def test_streaming_checkpoint_path_resolution(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    expected_dead_letter: str,
    expected_reconciliation: str,
) -> None:
    streaming_job = _load_streaming_job(monkeypatch, environment)

    assert streaming_job.DEAD_LETTER_CHECKPOINT_PATH == expected_dead_letter
    assert streaming_job.RECONCILIATION_CHECKPOINT_PATH == expected_reconciliation


def test_streaming_compose_defaults_to_loud_offset_loss() -> None:
    source = (REPO_ROOT / "docker-compose.extended.yml").read_text(encoding="utf-8")

    assert "KAFKA_FAIL_ON_DATA_LOSS: ${KAFKA_FAIL_ON_DATA_LOSS:-true}" in source
    assert "orders_dead_letter" in source
    assert "orders_reconciliation" in source
