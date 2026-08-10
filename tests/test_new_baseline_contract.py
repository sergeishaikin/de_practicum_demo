"""Offline contract checks for the deliberate B2 new-baseline epoch.

These tests intentionally inspect the producer/Spark/writer source and Compose
configuration instead of starting Kafka, Spark, MinIO, or the Iceberg catalog.
The new epoch is a stateful rollout concern; its unit contract must remain
deterministic and reviewable without mutating any runtime state.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import types
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCER_PATH = REPO_ROOT / "kafka" / "producer" / "orders_producer.py"
SPARK_PATH = REPO_ROOT / "spark" / "jobs" / "orders_streaming.py"
WRITER_PATH = REPO_ROOT / "iceberg" / "writer" / "iceberg_writer.py"
COMPOSE_EXTENDED_PATH = REPO_ROOT / "docker-compose.extended.yml"


def _load_producer(monkeypatch: pytest.MonkeyPatch):
    """Load the producer with a local Kafka stub (no broker/client needed)."""

    monkeypatch.setenv("SOURCE_EPOCH_ID", "test-new-baseline-epoch")
    kafka_stub = types.ModuleType("confluent_kafka")
    kafka_stub.Producer = type("Producer", (), {})
    previous = sys.modules.get("confluent_kafka")
    sys.modules["confluent_kafka"] = kafka_stub
    try:
        spec = importlib.util.spec_from_file_location("_test_orders_producer", PRODUCER_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("confluent_kafka", None)
        else:
            sys.modules["confluent_kafka"] = previous


def test_canonical_payload_is_sorted_compact_domain_json_and_hash_stable(monkeypatch) -> None:
    producer = _load_producer(monkeypatch)
    domain = {
        "order_id": "order-1",
        "customer": "Alice",
        "amount": 12.5,
        "country": "UK",
        "status": "paid",
        "business_version": 1,
        "event_time": "2026-08-10T12:00:00+00:00",
    }
    reordered_with_transport = {
        "event_time": domain["event_time"],
        "status": domain["status"],
        "order_id": domain["order_id"],
        "customer": domain["customer"],
        "amount": domain["amount"],
        "country": domain["country"],
        "business_version": domain["business_version"],
        "event_id": "transport-id-must-not-affect-canonical-bytes",
    }

    canonical_a = producer.canonical_payload_bytes(domain)
    canonical_b = producer.canonical_payload_bytes(reordered_with_transport)
    assert canonical_a == canonical_b
    assert canonical_a == json.dumps(
        domain,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert producer.canonical_payload_hash(canonical_a) == hashlib.sha256(canonical_a).hexdigest()


def test_new_epoch_events_have_non_null_epoch_unique_event_id_and_matching_lineage(monkeypatch) -> None:
    producer = _load_producer(monkeypatch)
    first = producer.create_event()
    second = producer.create_event()

    assert first["source_epoch_id"] == "test-new-baseline-epoch"
    assert first["source_epoch_id"]
    assert first["event_id"] and first["event_id"] != second["event_id"]
    uuid.UUID(first["event_id"])
    canonical = first["canonical_payload"]
    canonical_bytes = canonical.encode("utf-8") if isinstance(canonical, str) else canonical
    assert first["canonical_payload_hash"] == hashlib.sha256(canonical_bytes).hexdigest()
    assert json.loads(canonical_bytes) == {
        key: first[key]
        for key in producer.DOMAIN_FIELDS
    }


def test_spark_rejects_wrong_epoch_hash_mismatch_and_duplicate_event_ids() -> None:
    source = SPARK_PATH.read_text(encoding="utf-8")
    for field in ("source_epoch_id", "event_id", "canonical_payload", "canonical_payload_hash"):
        assert field in source
        assert re.search(rf'StructField\("{field}"', source)
    assert "dropDuplicates" in source and re.search(
        r"dropDuplicates\s*\(\s*\[\s*[\"']event_id[\"']", source
    )
    assert re.search(r"sha2\s*\(.*canonical_payload", source, flags=re.DOTALL)
    assert re.search(r"source_epoch_id.*SOURCE_EPOCH_ID|SOURCE_EPOCH_ID.*source_epoch_id", source)
    assert "KAFKA_FAIL_ON_DATA_LOSS" in source


def test_landing_and_bronze_declarations_preserve_all_lineage_fields() -> None:
    spark = SPARK_PATH.read_text(encoding="utf-8")
    writer = WRITER_PATH.read_text(encoding="utf-8")
    lineage_fields = ("source_epoch_id", "event_id", "canonical_payload", "canonical_payload_hash")
    for field in lineage_fields:
        assert re.search(rf'StructField\("{field}"', spark)
        assert re.search(rf'NestedField\([^\n]*"{field}"', writer)
    assert ".format(\"parquet\")" in spark or ".format('parquet')" in spark
    assert "canonical_payload_hash" in writer


def test_named_kafka_volume_and_new_checkpoints_leave_historical_defaults_intact() -> None:
    compose = COMPOSE_EXTENDED_PATH.read_text(encoding="utf-8")
    assert "de_demo_kafka_data:/var/lib/kafka/data" in compose
    assert re.search(r"KAFKA_LOG_DIRS:\s*/var/lib/kafka/data", compose)
    assert "SOURCE_EPOCH_ID" in compose
    assert "NEW_BASELINE_CHECKPOINT_ROOT" in compose
    for name in (
        "NEW_BASELINE_RAW_CHECKPOINT_PATH",
        "NEW_BASELINE_POSTGRES_CHECKPOINT_PATH",
        "NEW_BASELINE_DEAD_LETTER_CHECKPOINT_PATH",
        "NEW_BASELINE_RECONCILIATION_CHECKPOINT_PATH",
    ):
        assert re.search(rf"^\s+{name}:", compose, flags=re.MULTILINE)
    assert "checkpoints/b2-new-baseline/" in compose

    spark = SPARK_PATH.read_text(encoding="utf-8")
    historical = {
        "RAW_CHECKPOINT_PATH": "checkpoints/orders_raw",
        "POSTGRES_CHECKPOINT_PATH": "checkpoints/orders_postgres",
        "DEAD_LETTER_CHECKPOINT_PATH": "checkpoints/orders_dead_letter",
        "RECONCILIATION_CHECKPOINT_PATH": "checkpoints/orders_reconciliation",
    }
    for name, suffix in historical.items():
        assert name in spark
        assert suffix in spark


def test_readiness_receipt_semantics_are_fail_closed_and_deterministic() -> None:
    """READY is the sole authorization; every other disposition is STOP."""

    def authorized(receipt: dict) -> bool:
        return (
            receipt.get("disposition") == "READY"
            and receipt.get("ready_for_01_02c") is True
            and receipt.get("historical_continuity_claimed") is False
            and receipt.get("old_checkpoints_untouched") is True
        )

    ready = {
        "disposition": "READY",
        "ready_for_01_02c": True,
        "historical_continuity_claimed": False,
        "old_checkpoints_untouched": True,
    }
    stop = {**ready, "disposition": "STOP", "ready_for_01_02c": False}
    contradictory = {**ready, "disposition": "STOP"}
    assert authorized(ready)
    assert not authorized(stop)
    assert not authorized(contradictory)

    # Task 3 emits this artifact only after the stateful bounded epoch.  When
    # present, validate its persisted contract as well; absence is expected
    # during the read-only Task 1 test gate.
    receipt_path = REPO_ROOT / "artifacts" / "b2-rollout" / "02b-new-baseline-readiness.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt.get("historical_continuity_claimed") is False
        assert receipt.get("old_checkpoints_untouched") is True
        assert receipt.get("ready_for_01_02c") is (receipt.get("disposition") == "READY")
