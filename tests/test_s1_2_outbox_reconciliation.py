from __future__ import annotations

from iceberg.medallion.legacy_outbox_reconciliation import (
    SnapshotEvidence,
    classify_manifests,
    cleanup_set_digest,
)


def row(order_id: str, version: int | None, amount: float = 10.0) -> dict:
    return {
        "order_id": order_id,
        "customer": "customer",
        "amount": amount,
        "country": "DE",
        "status": "paid",
        "event_time": "2026-01-01T12:00:00",
        "event_date": "2026-01-01",
        "business_version": version,
    }


def manifest(load_id: str, path: str = "data/file.parquet") -> dict:
    return {
        "load_id": load_id,
        "_object_path": f"bucket/outbox/{load_id}.json",
        "bronze_data_files": [path],
        "source_paths": [f"landing/{load_id}.parquet"],
    }


def snapshot(load_id: str, timestamp_ms: int = 100) -> SnapshotEvidence:
    return SnapshotEvidence(
        snapshot_id=f"snapshot-{load_id}",
        timestamp_ms=timestamp_ms,
        load_id=load_id,
        migration_marker=None,
    )


def classify(records, rows_by_load, bronze, silver, *, progress=None, ts=100):
    return classify_manifests(
        records,
        rows_by_load,
        bronze,
        silver,
        {record["load_id"]: [snapshot(record["load_id"], ts)] for record in records},
        SnapshotEvidence(
            "migration", 200, None, "legacy-singleton-business-version-v1"
        ),
        progress or {"work": {}, "completed": {}},
    )


def test_legacy_row_is_safe_only_after_authoritative_v1_match() -> None:
    record = manifest("load-a")
    result = classify(
        [record],
        {"load-a": [row("order-a", None)]},
        [row("order-a", 1)],
        [row("order-a", 1)],
    )

    assert result["safe_stale"] == 1
    assert result["blocked"] == 0
    assert result["legacy_null_physical_rows"] == 1


def test_active_progress_blocks_even_when_rows_are_migrated() -> None:
    record = manifest("load-a")
    result = classify(
        [record],
        {"load-a": [row("order-a", None)]},
        [row("order-a", 1)],
        [row("order-a", 1)],
        progress={"work": {"load-a": {"status": "in_flight"}}, "completed": {}},
    )

    assert result["safe_stale"] == 0
    assert result["in_flight_blocked"] == 1
    assert result["blocked"] == 0
    assert result["blocked_reasons"] == {"active_or_inflight_progress": 1}


def test_missing_authoritative_row_blocks_cleanup() -> None:
    record = manifest("load-a")
    result = classify(
        [record],
        {"load-a": [row("order-a", None)]},
        [],
        [],
    )

    assert result["blocked"] == 1
    assert (
        "rows_not_fully_represented_in_authoritative_bronze"
        in result["blocked_reasons"]
    )
    assert "order_id_missing_from_authoritative_bronze" in result["blocked_reasons"]


def test_cleanup_digest_is_order_independent() -> None:
    left = [
        {"load_id": "b", "manifest": "bucket/b.json"},
        {"load_id": "a", "manifest": "bucket/a.json"},
    ]
    right = list(reversed(left))

    assert cleanup_set_digest(left) == cleanup_set_digest(right)


def test_post_migration_snapshot_is_blocked() -> None:
    record = manifest("load-a")
    result = classify(
        [record],
        {"load-a": [row("order-a", None)]},
        [row("order-a", 1)],
        [row("order-a", 1)],
        ts=300,
    )

    assert result["live_post_migration"] == 1
    assert result["blocked"] == 0
    assert result["blocked_reasons"] == {}
