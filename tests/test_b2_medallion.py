from __future__ import annotations

import io
import json
from datetime import date, datetime
from types import SimpleNamespace

import pyarrow as pa
import pytest
from pyarrow.fs import FileInfo, FileType

from b2_spike import collapse_delta, resolve_against_current
from medallion import iceberg_medallion as m

TS = datetime(2026, 1, 1, 12, 0, 0)


def row(
    order_id: str,
    version: int,
    *,
    amount: float,
    customer: str | None = None,
    event_date: date = date(2026, 1, 1),
) -> dict:
    return {
        "order_id": order_id,
        "customer": customer or f"customer-{order_id}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": TS,
        "kafka_timestamp": TS,
        "kafka_partition": 0,
        "kafka_offset": version,
        "event_date": event_date,
        "business_version": version,
    }


def rows_to_arrow(rows: list[dict]) -> pa.Table:
    return pa.table(
        {
            name: pa.array(
                [item.get(name) for item in rows],
                type=m._SILVER_TYPES[name],
            )
            for name in m._SILVER_TYPES
        }
    )


class OutputStream(io.BytesIO):
    def __init__(self, fs: "FakeFS", path: str) -> None:
        super().__init__()
        self.fs = fs
        self.path = path

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.fs.objects[self.path] = self.getvalue()
        return False


class FakeFS:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def get_file_info(self, selector) -> list[FileInfo]:
        return [
            FileInfo(path, type=FileType.File)
            for path in sorted(self.objects)
            if path.startswith(selector.base_dir)
        ]

    def open_input_file(self, path: str):
        try:
            return io.BytesIO(self.objects[path])
        except KeyError as exc:
            raise FileNotFoundError(path) from exc

    def open_output_stream(self, path: str):
        return OutputStream(self, path)

    def delete_file(self, path: str) -> None:
        del self.objects[path]


class FakeScan:
    def __init__(self, table: "FakeIcebergTable", row_filter=None) -> None:
        self.table = table
        self.row_filter = row_filter

    def to_arrow(self) -> pa.Table:
        rows = self.table.rows
        values = predicate_values(self.row_filter)
        if values is not None:
            rows = [item for item in rows if item["order_id"] in values]
        return rows_to_arrow(rows)


class FakeIcebergTable:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.metadata = SimpleNamespace(snapshots=[])

    def scan(self, row_filter=None) -> FakeScan:
        return FakeScan(self, row_filter)

    def overwrite(self, arrow_table, overwrite_filter, snapshot_properties=None) -> None:
        values = predicate_values(overwrite_filter)
        self.rows = [item for item in self.rows if item["order_id"] not in values]
        self.rows.extend(arrow_table.to_pylist())
        snapshot_id = len(self.metadata.snapshots) + 1
        self.metadata.snapshots.append(
            SimpleNamespace(
                snapshot_id=snapshot_id,
                summary=SimpleNamespace(
                    additional_properties=snapshot_properties or {}
                ),
            )
        )

    def current_snapshot(self):
        return self.metadata.snapshots[-1] if self.metadata.snapshots else None


def predicate_values(predicate) -> set[str]:
    literals = getattr(predicate, "literals", None)
    if literals is not None:
        return {literal.value for literal in literals}
    literal = getattr(predicate, "literal", None)
    return {literal.value} if literal is not None else set()


class FakeCatalog:
    def __init__(self, bronze: FakeIcebergTable, silver: FakeIcebergTable) -> None:
        self.tables = {
            "bronze.orders": bronze,
            "silver.orders_clean": silver,
        }

    def load_table(self, identifier: str):
        return self.tables[identifier]


class FakeMetrics:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


def outbox(load_id: str) -> tuple[str, bytes]:
    path = f"de-practicum/test-outbox/{load_id}.json"
    payload = {
        "version": 1,
        "load_id": load_id,
        "source_paths": [f"de-practicum/landing/{load_id}.parquet"],
        "bronze_data_files": [f"de-practicum/bronze/{load_id}.parquet"],
        "row_count": 1,
    }
    return path, json.dumps(payload).encode("utf-8")


def setup_run(monkeypatch, incoming: list[dict], silver_rows: list[dict] | None = None):
    load_id = "load-1"
    object_path, payload = outbox(load_id)
    fs = FakeFS({object_path: payload})
    bronze = FakeIcebergTable()
    silver = FakeIcebergTable(silver_rows)
    catalog = FakeCatalog(bronze, silver)
    monkeypatch.setattr(m, "MINIO_BUCKET", "de-practicum")
    monkeypatch.setattr(m, "BRONZE_OUTBOX_PREFIX", "test-outbox")
    monkeypatch.setattr(m, "MEDALLION_PROGRESS_PATH", "test-progress/progress.json")
    monkeypatch.setattr(m, "ensure_table", lambda *args: None)
    monkeypatch.setattr(m, "read_bronze_work", lambda fs, bronze, record: rows_to_arrow(incoming))
    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_BEFORE_COMMIT", False)
    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_AFTER_COMMIT", False)
    monkeypatch.setattr(
        m.os,
        "_exit",
        lambda code: (_ for _ in ()).throw(SystemExit(code)),
    )
    return fs, catalog, silver, FakeMetrics(), load_id


def test_resolution_is_business_version_only_and_collapses_batch() -> None:
    same_batch = [
        row("a", 3, amount=30),
        row("a", 5, amount=50),
        row("b", 1, amount=10),
    ]
    assert collapse_delta(same_batch)[0]["business_version"] == 5
    current = [row("a", 5, amount=50)]
    assert resolve_against_current(current, [row("a", 3, amount=30)]) == []


def test_ff14_rejects_before_silver_mutation() -> None:
    conflicting = [
        row("a", 4, amount=40, customer="first"),
        row("a", 4, amount=41, customer="second"),
    ]
    with pytest.raises(ValueError, match="FF-14"):
        collapse_delta(conflicting)


def test_completed_progress_is_bounded(monkeypatch) -> None:
    progress = {
        "completed": {
            "old": {"sequence": 1},
            "new": {"sequence": 2},
        }
    }
    monkeypatch.setattr(m, "MAX_COMPLETED_PROGRESS", 1)
    m._prune_completed(progress)
    assert progress["completed"] == {"new": {"sequence": 2}}


def test_b2_run_commits_only_advancing_keys_and_completes_progress(monkeypatch) -> None:
    incoming = [
        row("a", 3, amount=30, event_date=date(2026, 1, 2)),
        row("a", 5, amount=50, event_date=date(2026, 1, 2)),
        row("b", 2, amount=20),
    ]
    fs, catalog, silver, metrics, load_id = setup_run(monkeypatch, incoming, [row("a", 1, amount=10)])

    m.run_b2(catalog, metrics, fs)

    state = json.loads(fs.objects["de-practicum/test-progress/progress.json"])
    assert load_id in state["completed"]
    assert state["work"] == {}
    assert len(silver.rows) == 2
    by_id = {item["order_id"]: item for item in silver.rows}
    assert by_id["a"]["business_version"] == 5
    assert by_id["a"]["event_date"] == date(2026, 1, 2)
    assert by_id["b"]["business_version"] == 2
    assert metrics.records[-1]["status"] == "success"
    assert metrics.records[-1]["keys_processed"] == 2
    assert metrics.records[-1]["work_in_flight"] == 0
    assert metrics.records[-1]["work_completed"] == 1
    assert f"de-practicum/test-outbox/{load_id}.json" not in fs.objects

    snapshots = len(silver.metadata.snapshots)
    duplicate_path, duplicate_payload = outbox(load_id)
    fs.objects[duplicate_path] = duplicate_payload
    m.run_b2(catalog, metrics, fs)
    assert len(silver.metadata.snapshots) == snapshots
    assert f"de-practicum/test-outbox/{load_id}.json" not in fs.objects


def test_b2_crash_before_commit_retries(monkeypatch) -> None:
    fs, catalog, silver, metrics, _ = setup_run(monkeypatch, [row("a", 1, amount=10)])
    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_BEFORE_COMMIT", True)
    with pytest.raises(SystemExit) as exc:
        m.run_b2(catalog, metrics, fs)
    assert exc.value.code == 21
    assert silver.rows == []
    progress = json.loads(fs.objects["de-practicum/test-progress/progress.json"])
    assert progress["work"]["load-1"]["status"] == "in_flight"

    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_BEFORE_COMMIT", False)
    m.run_b2(catalog, metrics, fs)
    assert len(silver.rows) == 1
    assert not json.loads(fs.objects["de-practicum/test-progress/progress.json"])["work"]


def test_recovery_acknowledgement_can_leave_manifest_for_separate_cleanup(
    monkeypatch,
) -> None:
    fs, catalog, silver, metrics, load_id = setup_run(
        monkeypatch, [row("a", 1, amount=10)]
    )
    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_BEFORE_COMMIT", True)
    with pytest.raises(SystemExit):
        m.run_b2(catalog, metrics, fs)

    progress = json.loads(fs.objects["de-practicum/test-progress/progress.json"])
    record = m.list_bronze_work(fs)[0]
    m._mark_b2_completed(
        fs,
        progress,
        record,
        snapshot_id=None,
        changed_keys=[],
        delete_outbox=False,
    )

    state = json.loads(fs.objects["de-practicum/test-progress/progress.json"])
    assert state["work"] == {}
    assert load_id in state["completed"]
    assert record["_object_path"] in fs.objects
    assert silver.rows == []


def test_b2_crash_after_commit_reconciles_without_second_snapshot(monkeypatch) -> None:
    fs, catalog, silver, metrics, _ = setup_run(monkeypatch, [row("a", 1, amount=10)])
    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_AFTER_COMMIT", True)
    with pytest.raises(SystemExit) as exc:
        m.run_b2(catalog, metrics, fs)
    assert exc.value.code == 22
    assert len(silver.rows) == 1
    assert len(silver.metadata.snapshots) == 1

    monkeypatch.setattr(m, "SIMULATE_B2_CRASH_AFTER_COMMIT", False)
    m.run_b2(catalog, metrics, fs)
    assert len(silver.rows) == 1
    assert len(silver.metadata.snapshots) == 1
    progress = json.loads(fs.objects["de-practicum/test-progress/progress.json"])
    assert progress["work"] == {}
    assert progress["completed"]["load-1"]["silver_snapshot_id"] == 1
