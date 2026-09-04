from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from medallion import iceberg_medallion as m
from medallion import legacy_outbox_reconciliation as r
from medallion.legacy_business_version_migration import MIGRATION_MARKER
from medallion.legacy_outbox_reconciliation import (
    SnapshotEvidence,
    build_live_receipt,
    classify_manifests,
    cleanup_set_digest,
    migration_boundary,
    reconcile_inflight_noop,
    snapshot_evidence,
)
from tests.support.b2_fakes import (
    BASE_TIMESTAMP_MS,
    FakeCatalog,
    FakeFS,
    FakeIcebergTable,
    rows_to_arrow,
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


# --------------------------------------------------------------------------
# Classifier evidence gaps
# --------------------------------------------------------------------------


def test_manifest_without_physical_file_provenance_is_blocked() -> None:
    record = {
        "load_id": "load-a",
        "_object_path": "bucket/outbox/load-a.json",
        "bronze_data_files": [],
        "source_paths": [],
    }

    result = classify([record], {"load-a": []}, [], [])

    assert result["blocked"] == 1
    assert result["blocked_reasons"] == {"no_physical_file_provenance": 1}


def test_unknown_and_ambiguous_snapshot_history_both_block_cleanup() -> None:
    unknown = manifest("load-unknown")
    ambiguous = manifest("load-ambiguous")
    boundary = SnapshotEvidence("migration", 200, None, MIGRATION_MARKER)

    result = classify_manifests(
        [unknown, ambiguous],
        {"load-unknown": [], "load-ambiguous": []},
        [],
        [],
        {
            "load-ambiguous": [
                snapshot("load-ambiguous", 100),
                snapshot("load-ambiguous", 150),
            ]
        },
        boundary,
        {"work": {}, "completed": {}},
    )

    reasons = {
        item["load_id"]: item["blocked_reasons"] for item in result["dispositions"]
    }
    assert reasons["load-unknown"] == ["load_id_not_found_in_bronze_snapshot_history"]
    assert reasons["load-ambiguous"] == ["load_id_has_ambiguous_bronze_snapshots"]
    assert result["blocked"] == 2


def test_null_order_id_blocks_cleanup_without_consuming_authoritative_rows() -> None:
    record = manifest("load-a")

    result = classify(
        [record],
        {"load-a": [row(None, None), row("order-a", 1)]},
        [row("order-a", 1)],
        [row("order-a", 1)],
    )

    assert result["blocked"] == 1
    assert result["blocked_reasons"] == {"null_order_id": 1}
    # The null row is skipped, not counted as an unmatched physical row.
    assert result["logical_rows"] == 2
    assert result["versioned_physical_rows"] == 1
    assert result["legacy_null_physical_rows"] == 0


def test_silver_gaps_and_stale_versions_block_cleanup() -> None:
    missing = manifest("load-missing")
    stale = manifest("load-stale")
    boundary = SnapshotEvidence("migration", 200, None, MIGRATION_MARKER)

    result = classify_manifests(
        [missing, stale],
        {"load-missing": [row("order-b", 1)], "load-stale": [row("order-c", 2)]},
        [row("order-b", 1), row("order-c", 2)],
        [row("order-c", 1)],
        {
            "load-missing": [snapshot("load-missing", 100)],
            "load-stale": [snapshot("load-stale", 100)],
        },
        boundary,
        {"work": {}, "completed": {}},
    )

    reasons = {
        item["load_id"]: item["blocked_reasons"] for item in result["dispositions"]
    }
    assert reasons["load-missing"] == ["order_id_missing_from_current_silver"]
    assert reasons["load-stale"] == ["silver_not_at_authoritative_b2_version"]


def test_progress_matching_uses_file_provenance_not_only_load_id() -> None:
    record = manifest("load-a", path="shared/file.parquet")
    progress = {
        "work": {
            "load-retried": {
                "status": "in_flight",
                "bronze_data_files": ["shared/file.parquet"],
                "source_paths": [],
            }
        },
        "completed": {},
    }

    result = classify(
        [record],
        {"load-a": [row("order-a", 1)]},
        [row("order-a", 1)],
        [row("order-a", 1)],
        progress=progress,
    )

    assert result["in_flight_blocked"] == 1
    assert result["dispositions"][0]["active_progress_refs"] == ["load-retried"]


def test_repeated_manifests_cannot_both_claim_the_same_authoritative_row() -> None:
    first = manifest("load-a")
    second = manifest("load-b")

    result = classify(
        [first, second],
        {"load-a": [row("order-a", 1)], "load-b": [row("order-a", 1)]},
        [row("order-a", 1)],
        [row("order-a", 1)],
    )

    assert result["safe_stale"] == 1
    assert result["blocked"] == 1
    assert result["blocked_reasons"] == {
        "rows_not_fully_represented_in_authoritative_bronze": 1
    }


def test_migration_boundary_is_the_latest_marked_snapshot() -> None:
    early = SnapshotEvidence(1, 100, None, MIGRATION_MARKER)
    late = SnapshotEvidence(2, 300, None, MIGRATION_MARKER)
    unrelated = SnapshotEvidence(3, 400, "load-a", None)

    assert migration_boundary([early, late, unrelated]) is late
    assert migration_boundary([unrelated]) is None


def test_migration_boundary_breaks_timestamp_ties_on_snapshot_id() -> None:
    lower = SnapshotEvidence("aaa", 100, None, MIGRATION_MARKER)
    higher = SnapshotEvidence("bbb", 100, None, MIGRATION_MARKER)

    assert migration_boundary([higher, lower]) is higher


def test_snapshot_timestamp_is_rendered_as_utc_iso() -> None:
    evidence = SnapshotEvidence(1, 1_767_225_600_500, None, None)

    assert evidence.timestamp_iso == "2026-01-01T00:00:00.500000+00:00"


def test_canonical_rows_normalise_bytes_and_temporal_values() -> None:
    canonical = dict(
        r._canonical_row(
            {
                "checksum": b"\x00\xff",
                "event_time": datetime(2026, 1, 1, 12),
                "event_date": date(2026, 1, 1),
            }
        )
    )

    assert canonical["checksum"] == "00ff"
    assert canonical["event_time"] == "2026-01-01T12:00:00"
    assert canonical["event_date"] == "2026-01-01"


def test_legacy_normalisation_applies_to_rows_without_a_version_column() -> None:
    absent = dict(r._canonical_row({"order_id": "a"}, normalize_legacy=True))
    explicit_null = dict(
        r._canonical_row(
            {"order_id": "a", "business_version": None}, normalize_legacy=True
        )
    )

    assert absent["business_version"] == 1
    assert explicit_null["business_version"] == 1


# --------------------------------------------------------------------------
# Live evidence: S1.2A.1 recovery and the dry-run receipt
# --------------------------------------------------------------------------

BUCKET = "de-practicum"
OUTBOX_PREFIX = "test-outbox"
PROGRESS_PATH = "test-progress/progress.json"
LEDGER_PREFIX = "test-completion-ledger"
PROGRESS_OBJECT = f"{BUCKET}/{PROGRESS_PATH}"
DATA_FILE = f"{BUCKET}/bronze/load-1.parquet"


def physical_row(
    order_id: str | None,
    version: int | None,
    *,
    amount: float = 10.0,
    offset: int = 0,
    event_day: date = date(2026, 1, 1),
) -> dict:
    """A Bronze row as it exists physically, with real Arrow-compatible types.

    ``offset`` is independent of ``business_version`` on purpose: the legacy
    normalisation must make a NULL-version row canonically identical to its
    migrated counterpart, which only holds if no other column tracks the
    version.
    """

    timestamp = datetime(event_day.year, event_day.month, event_day.day, 12)
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}",
        "amount": amount,
        "country": "DE",
        "status": "paid",
        "event_time": timestamp,
        "kafka_timestamp": timestamp,
        "kafka_partition": 0,
        "kafka_offset": offset,
        "event_date": event_day,
        "business_version": version,
    }


def outbox_bytes(load_id: str, *, files: tuple[str, ...] = (DATA_FILE,)) -> bytes:
    return json.dumps(
        {
            "version": 1,
            "load_id": load_id,
            "source_paths": [f"{BUCKET}/landing/{load_id}.parquet"],
            "bronze_data_files": list(files),
            "row_count": 1,
        }
    ).encode("utf-8")


def progress_bytes(*, work: dict | None = None, completed: dict | None = None) -> bytes:
    return json.dumps(
        {
            "version": 1,
            "next_sequence": 0,
            "work": work if work is not None else {},
            "completed": completed or {},
        }
    ).encode("utf-8")


def in_flight(load_id: str, *, files: tuple[str, ...] = (DATA_FILE,)) -> dict:
    return {
        load_id: {
            "status": "in_flight",
            "source_paths": [f"{BUCKET}/landing/{load_id}.parquet"],
            "bronze_data_files": list(files),
        }
    }


def use_fake_storage(monkeypatch) -> None:
    monkeypatch.setattr(m, "MINIO_BUCKET", BUCKET)
    monkeypatch.setattr(m, "BRONZE_OUTBOX_PREFIX", OUTBOX_PREFIX)
    monkeypatch.setattr(m, "MEDALLION_PROGRESS_PATH", PROGRESS_PATH)
    monkeypatch.setattr(m, "MEDALLION_COMPLETION_LEDGER_PREFIX", LEDGER_PREFIX)


def recovery_lake(
    monkeypatch,
    *,
    raw_rows: list[dict],
    bronze_rows: list[dict],
    silver_rows: list[dict],
    load_id: str = "load-1",
    work: dict | None = None,
    completed: dict | None = None,
    manifests: tuple[str, ...] = ("load-1",),
):
    objects = {
        f"{BUCKET}/{OUTBOX_PREFIX}/{name}.json": outbox_bytes(name)
        for name in manifests
    }
    objects[PROGRESS_OBJECT] = progress_bytes(
        work=in_flight(load_id) if work is None else work,
        completed=completed,
    )
    fs = FakeFS(objects)
    bronze = FakeIcebergTable(list(bronze_rows))
    silver = FakeIcebergTable(list(silver_rows))
    use_fake_storage(monkeypatch)
    monkeypatch.setattr(
        r,
        "read_bronze_work",
        lambda filesystem, table, record: rows_to_arrow(list(raw_rows)),
    )
    return fs, FakeCatalog(bronze, silver), bronze, silver


def state(fs: FakeFS, silver: FakeIcebergTable) -> tuple:
    """Everything S1.2A.1 must not disturb when it fails closed."""

    return dict(fs.objects), list(silver.rows), len(silver.metadata.snapshots)


def test_recovery_fails_closed_when_the_manifest_is_absent(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        manifests=(),
    )
    before = state(fs, silver)

    with pytest.raises(RuntimeError, match="manifest not found: load-1"):
        reconcile_inflight_noop(catalog, fs, "load-1")

    assert state(fs, silver) == before


def test_recovery_fails_closed_when_the_work_is_not_in_flight(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        work={},
    )
    before = state(fs, silver)

    with pytest.raises(RuntimeError, match="work is not in-flight: load-1"):
        reconcile_inflight_noop(catalog, fs, "load-1")

    assert state(fs, silver) == before


def test_recovery_fails_closed_when_the_work_is_already_completed(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        completed={"load-1": {"sequence": 1}},
    )
    before = state(fs, silver)

    with pytest.raises(RuntimeError, match="work is already completed: load-1"):
        reconcile_inflight_noop(catalog, fs, "load-1")

    assert state(fs, silver) == before


def test_committed_silver_work_snapshot_defers_to_normal_recovery(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
    )
    silver.add_snapshot(**{"silver-work-id": "load-1"})
    before = state(fs, silver)

    with pytest.raises(RuntimeError, match="normal committed-snapshot recovery path"):
        reconcile_inflight_noop(catalog, fs, "load-1")

    assert state(fs, silver) == before


def test_recovery_fails_closed_when_a_raw_row_is_not_in_authoritative_bronze(
    monkeypatch,
) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None, amount=99.0)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
    )
    before = state(fs, silver)

    with pytest.raises(RuntimeError, match="not represented in authoritative Bronze"):
        reconcile_inflight_noop(catalog, fs, "load-1")

    assert state(fs, silver) == before


def test_recovery_fails_closed_when_silver_still_needs_the_work(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[],
    )
    before = state(fs, silver)

    with pytest.raises(RuntimeError, match="is not a no-op"):
        reconcile_inflight_noop(catalog, fs, "load-1")

    assert state(fs, silver) == before


def test_genuine_noop_completes_progress_and_keeps_the_manifest(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
    )
    silver_before = list(silver.rows)

    result = reconcile_inflight_noop(catalog, fs, "load-1")

    assert result == {
        "load_id": "load-1",
        "raw_rows": 1,
        "normalized_legacy_rows": 1,
        "resolved_rows": 0,
        "silver_snapshot_id": None,
        "progress_completed": True,
        "manifest_deleted": False,
    }
    progress = json.loads(fs.objects[PROGRESS_OBJECT])
    assert progress["work"] == {}
    assert progress["completed"]["load-1"] == {
        "sequence": 1,
        "silver_snapshot_id": None,
        "changed_keys": [],
    }
    # The manifest survives for the separately approved S1.2B cleanup, and
    # Silver is never rewritten by a recovery acknowledgement.
    assert f"{BUCKET}/{OUTBOX_PREFIX}/load-1.json" in fs.objects
    assert silver.rows == silver_before
    assert silver.metadata.snapshots == []
    receipt = json.loads(fs.objects[f"{BUCKET}/{LEDGER_PREFIX}/load-1.json"])
    assert receipt["result"] == "success"
    assert receipt["load_id"] == "load-1"
    assert receipt["silver_snapshot_id"] is None


def test_already_versioned_rows_report_no_legacy_normalisation(monkeypatch) -> None:
    fs, catalog, _bronze, _silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", 2)],
        bronze_rows=[physical_row("a", 2)],
        silver_rows=[physical_row("a", 2)],
    )

    result = reconcile_inflight_noop(catalog, fs, "load-1")

    assert result["normalized_legacy_rows"] == 0
    assert result["raw_rows"] == 1
    assert result["progress_completed"] is True


def test_silver_snapshot_id_is_reported_when_silver_has_history(monkeypatch) -> None:
    fs, catalog, _bronze, silver = recovery_lake(
        monkeypatch,
        raw_rows=[physical_row("a", None)],
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
    )
    silver.add_snapshot(**{"added-data-files": "1"})

    result = reconcile_inflight_noop(catalog, fs, "load-1")

    assert result["silver_snapshot_id"] == 1
    assert len(silver.metadata.snapshots) == 1


def receipt_lake(
    monkeypatch,
    *,
    bronze_rows: list[dict],
    silver_rows: list[dict],
    rows_by_load: dict[str, list[dict]],
    manifests: dict[str, tuple[str, ...]] | None = None,
    work: dict | None = None,
    load_snapshots: tuple[str, ...] = ("load-1",),
    boundary: bool = True,
):
    manifests = manifests or {name: (DATA_FILE,) for name in rows_by_load}
    objects = {
        f"{BUCKET}/{OUTBOX_PREFIX}/{name}.json": outbox_bytes(name, files=files)
        for name, files in manifests.items()
    }
    objects[PROGRESS_OBJECT] = progress_bytes(work=work)
    fs = FakeFS(objects)
    bronze = FakeIcebergTable(list(bronze_rows))
    silver = FakeIcebergTable(list(silver_rows))
    for name in load_snapshots:
        bronze.add_snapshot(**{"load-id": name})
    if boundary:
        bronze.add_snapshot(**{"business-version-migration": MIGRATION_MARKER})
    reads: list[str] = []

    def fake_read(filesystem, table, record):
        reads.append(record["load_id"])
        return rows_to_arrow(list(rows_by_load.get(record["load_id"], [])))

    use_fake_storage(monkeypatch)
    monkeypatch.setattr(r, "read_bronze_work", fake_read)
    return fs, FakeCatalog(bronze, silver), bronze, silver, reads


def test_receipt_describes_a_migrated_lake_as_safe_to_clean(monkeypatch) -> None:
    fs, catalog, _bronze, silver, reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", None)]},
    )
    silver.add_snapshot(**{"added-data-files": "1"})

    receipt = build_live_receipt(catalog, fs)

    assert receipt["migration"] == "S1.2"
    assert receipt["phase"] == "dry-run"
    assert receipt["schema_version"] == 2
    assert receipt["safe_stale"] == 1
    assert receipt["blocked"] == 0
    assert receipt["in_flight_blocked"] == 0
    assert receipt["live_post_migration"] == 0
    assert receipt["cleanup_set"] == [
        {
            "load_id": "load-1",
            "manifest": f"{BUCKET}/{OUTBOX_PREFIX}/load-1.json",
        }
    ]
    assert receipt["cleanup_set_digest"] == cleanup_set_digest(receipt["cleanup_set"])
    assert receipt["legacy_null_physical_rows"] == 1
    assert receipt["versioned_physical_rows"] == 0
    assert receipt["bronze_snapshot_id"] == 2
    assert receipt["silver_snapshot_id"] == 1
    assert receipt["migration_snapshot_id"] == 2
    assert receipt["migration_boundary"] == "2026-01-01T00:00:02+00:00"
    assert receipt["migration_boundary_timestamp_ms"] == BASE_TIMESTAMP_MS + 2000
    assert receipt["bronze_null_business_version_rows"] == 0
    assert receipt["silver_null_business_version_rows"] == 0
    assert receipt["authoritative_bronze_rows"] == 1
    assert receipt["authoritative_silver_rows"] == 1
    assert receipt["silver_unique_order_ids"] is True
    assert receipt["silver_equals_b2_projection"] is True
    assert receipt["b2_projection_valid"] is True
    assert receipt["b2_projection_error"] is None
    assert receipt["inflight_progress_count"] == 0
    assert receipt["inflight_progress_load_ids"] == []
    assert datetime.fromisoformat(receipt["generated_at"]).tzinfo == timezone.utc
    assert reads == ["load-1"]


def test_manifest_without_physical_files_is_blocked_and_never_read(monkeypatch) -> None:
    fs, catalog, _bronze, _silver, reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", 1)]},
        manifests={"load-1": ()},
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["blocked"] == 1
    assert receipt["blocked_reasons"] == {"no_physical_file_provenance": 1}
    assert receipt["logical_rows"] == 0
    assert receipt["cleanup_set"] == []
    # No physical provenance means no physical read is even attempted.
    assert reads == []


def test_inflight_progress_is_reported_and_blocks_its_manifest(monkeypatch) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", 1)]},
        work=in_flight("load-1"),
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["inflight_progress_count"] == 1
    assert receipt["inflight_progress_load_ids"] == ["load-1"]
    assert receipt["in_flight_blocked"] == 1
    assert receipt["safe_stale"] == 0
    assert receipt["cleanup_set"] == []


def test_receipt_reports_silver_diverging_from_the_b2_projection(monkeypatch) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 2, amount=20.0)],
        silver_rows=[physical_row("a", 1, amount=10.0)],
        rows_by_load={"load-1": [physical_row("a", 2, amount=20.0)]},
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["silver_equals_b2_projection"] is False
    assert receipt["blocked"] == 1
    assert receipt["blocked_reasons"] == {"silver_not_at_authoritative_b2_version": 1}


def test_receipt_reports_a_non_unique_silver_grain(monkeypatch) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1), physical_row("a", 1, offset=7)],
        rows_by_load={"load-1": [physical_row("a", 1)]},
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["silver_unique_order_ids"] is False
    assert receipt["authoritative_silver_rows"] == 2
    assert receipt["silver_equals_b2_projection"] is False


def test_absent_migration_boundary_leaves_every_manifest_live(monkeypatch) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", 1)]},
        boundary=False,
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["migration_snapshot_id"] is None
    assert receipt["migration_boundary"] is None
    assert receipt["migration_boundary_timestamp_ms"] is None
    assert receipt["live_post_migration"] == 1
    assert receipt["safe_stale"] == 0
    assert receipt["cleanup_set"] == []


def test_unmigrated_bronze_is_reported_instead_of_crashing_the_receipt(
    monkeypatch,
) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", None)],
        silver_rows=[],
        rows_by_load={"load-1": [physical_row("a", None)]},
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["bronze_null_business_version_rows"] == 1
    assert receipt["b2_projection_valid"] is False
    assert receipt["b2_projection_error"] == (
        "Bronze contains rows without business_version; historical migration "
        "must complete before B2 reconciliation can be proven"
    )
    # Unprovable is never "proven equal".
    assert receipt["silver_equals_b2_projection"] is False
    assert receipt["authoritative_bronze_rows"] == 1


def test_unprovable_projection_withdraws_every_cleanup_candidate(monkeypatch) -> None:
    # A partially migrated lake: order "a" is migrated and its manifest would
    # otherwise classify clean, while order "b" is still a legacy NULL.
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1), physical_row("b", None)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", None)]},
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["b2_projection_valid"] is False
    assert receipt["safe_stale"] == 0
    assert receipt["blocked"] == 1
    assert receipt["cleanup_set"] == []
    assert receipt["cleanup_set_digest"] == cleanup_set_digest([])
    assert receipt["blocked_reasons"] == {"b2_projection_unproven": 1}
    assert receipt["dispositions"][0]["status"] == "BLOCKED"
    assert receipt["dispositions"][0]["blocked_reasons"] == ["b2_projection_unproven"]


def test_ff14_conflict_surfaces_the_underlying_projection_failure(monkeypatch) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[
            physical_row("a", 1, amount=10.0),
            physical_row("a", 1, amount=20.0, offset=1),
        ],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", 1, amount=10.0)]},
    )

    receipt = build_live_receipt(catalog, fs)

    assert receipt["bronze_null_business_version_rows"] == 0
    assert receipt["b2_projection_valid"] is False
    # No legacy NULLs, so the real cause is reported rather than the migration
    # message.
    assert receipt["b2_projection_error"].startswith(
        "B2 projection is not computable: FF-14"
    )
    assert receipt["safe_stale"] == 0
    assert receipt["cleanup_set"] == []


def test_snapshot_evidence_reads_load_ids_and_markers_from_summaries(
    monkeypatch,
) -> None:
    bronze = FakeIcebergTable([])
    bronze.add_snapshot(**{"load-id": "load-1"})
    bronze.add_snapshot(**{"business-version-migration": MIGRATION_MARKER})
    # A snapshot with no summary at all must still yield evidence, not crash.
    bronze.metadata.snapshots.append(
        SimpleNamespace(
            snapshot_id=3, timestamp_ms=BASE_TIMESTAMP_MS + 3000, summary=None
        )
    )

    evidence = snapshot_evidence(bronze)

    assert [item.load_id for item in evidence] == ["load-1", None, None]
    assert [item.migration_marker for item in evidence] == [
        None,
        MIGRATION_MARKER,
        None,
    ]
    assert evidence[0].timestamp_ms == BASE_TIMESTAMP_MS + 1000


def test_cli_writes_the_receipt_to_the_requested_evidence_path(
    monkeypatch, tmp_path, capsys
) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", None)]},
    )
    evidence = tmp_path / "nested" / "receipt.json"
    monkeypatch.setattr(r, "get_catalog", lambda: catalog)
    monkeypatch.setattr(r, "get_fs", lambda: fs)
    monkeypatch.setattr("sys.argv", ["reconcile", "--evidence", str(evidence)])

    r.main()

    written = json.loads(evidence.read_text(encoding="utf-8"))
    assert written["migration"] == "S1.2"
    assert written["safe_stale"] == 1
    assert json.loads(capsys.readouterr().out) == written


def test_cli_prints_the_receipt_without_an_evidence_path(monkeypatch, capsys) -> None:
    fs, catalog, _bronze, _silver, _reads = receipt_lake(
        monkeypatch,
        bronze_rows=[physical_row("a", 1)],
        silver_rows=[physical_row("a", 1)],
        rows_by_load={"load-1": [physical_row("a", None)]},
    )
    monkeypatch.setattr(r, "get_catalog", lambda: catalog)
    monkeypatch.setattr(r, "get_fs", lambda: fs)
    monkeypatch.setattr("sys.argv", ["reconcile"])

    r.main()

    assert json.loads(capsys.readouterr().out)["cleanup_set_digest"]
