from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pyarrow as pa
import pytest
from pyarrow.fs import FileInfo, FileType
from pyiceberg.exceptions import CommitFailedException, NoSuchTableError

from writer import iceberg_writer as w


class FakeSnap:
    def __init__(
        self, props: dict | None = None, snapshot_id: int | None = None
    ) -> None:
        self.snapshot_id = snapshot_id
        if props is None:
            self.summary = None
        else:
            self.summary = SimpleNamespace(additional_properties=props)


class FakeTable:
    def __init__(self, snapshots: list[FakeSnap] | None = None) -> None:
        self.metadata = SimpleNamespace(snapshots=snapshots or [])
        self.append_failures = 0
        self.append_calls: list[dict] = []

    def append(self, arrow_table, snapshot_properties: dict | None = None) -> None:
        self.append_calls.append(snapshot_properties)
        if self.append_failures > 0:
            self.append_failures -= 1
            raise CommitFailedException("simulated commit conflict")


class FakeCatalog:
    def __init__(self, table: FakeTable | None = None) -> None:
        self.table = table

    def load_table(self, identifier: str) -> FakeTable:
        if self.table is None:
            raise NoSuchTableError(identifier)
        return self.table


class FakeFS:
    def __init__(
        self, infos: list[FileInfo], metadata: dict[str, str] | None = None
    ) -> None:
        self.infos = infos
        self.metadata = metadata or {}

    def get_file_info(self, selector) -> list[FileInfo]:
        if "_spark_metadata" in selector.base_dir:
            return [
                FileInfo(path, type=FileType.File) for path in sorted(self.metadata)
            ]
        return self.infos

    def open_input_file(self, path: str):
        from io import BytesIO

        return BytesIO(self.metadata[path].encode("utf-8"))

    def open_input_stream(self, path: str):
        # The writer reads commit logs sequentially; the double mirrors the API
        # the production code actually calls.
        return self.open_input_file(path)


def spark_metadata(*paths: str) -> str:
    entries = [{"path": path, "action": "add"} for path in paths]
    return "v1\n" + "\n".join(json.dumps(entry) for entry in entries) + "\n"


class FakeMetrics:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


def settled_file(path: str, age_seconds: int) -> FileInfo:
    return FileInfo(
        path,
        size=10,
        type=FileType.File,
        mtime=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    )


class TestState:
    def test_roundtrip(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
        w.save_state({"a", "b"}, {"L1": ["x", "y"]})
        done, pending = w.load_state()
        assert done == {"a", "b"}
        assert pending == {"L1": ["x", "y"]}

    def test_legacy_list_format(self, tmp_path, monkeypatch) -> None:
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        monkeypatch.setattr(w, "STATE_FILE", state_file)
        done, pending = w.load_state()
        assert done == {"a", "b"}
        assert pending == {}

    def test_missing_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(w, "STATE_FILE", tmp_path / "nope.json")
        assert w.load_state() == (set(), {})

    def test_replace_failure_preserves_previous_valid_state(
        self, tmp_path, monkeypatch
    ) -> None:
        state_file = tmp_path / "state.json"
        monkeypatch.setattr(w, "STATE_FILE", state_file)
        w.save_state({"old"}, {"load-old": ["old.parquet"]})

        def fail_replace(source, target):
            raise OSError("simulated interruption before state replacement")

        monkeypatch.setattr(w.os, "replace", fail_replace)
        with pytest.raises(OSError, match="simulated interruption"):
            w.save_state({"new"}, {"load-new": ["new.parquet"]})

        assert w.load_state() == ({"old"}, {"load-old": ["old.parquet"]})
        assert list(tmp_path.glob(".*.tmp")) == []

    def test_state_is_fsynced_before_replace(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
        fsync_calls = []
        replace_calls = []
        real_replace = w.os.replace

        monkeypatch.setattr(w.os, "fsync", lambda fd: fsync_calls.append(fd))

        def record_replace(source, target):
            replace_calls.append((source, target))
            return real_replace(source, target)

        monkeypatch.setattr(w.os, "replace", record_replace)
        w.save_state({"a"}, {})

        assert len(fsync_calls) == 1
        assert len(replace_calls) == 1


class TestListNewFiles:
    def test_only_spark_committed_files_are_eligible(self) -> None:
        now = datetime.now(timezone.utc)
        base = "de-practicum/streaming/orders_raw"
        orphan_path = f"{base}/event_date=2026-01-01/orphan-old.parquet"
        committed_path = f"{base}/event_date=2026-01-01/committed.parquet"
        fs = FakeFS(
            [
                FileInfo(
                    orphan_path,
                    type=FileType.File,
                    mtime=now - timedelta(days=30),
                ),
                FileInfo(
                    committed_path,
                    type=FileType.File,
                    mtime=now,
                ),
                FileInfo("dir", type=FileType.Directory, mtime=now),
                FileInfo(
                    f"{base}/event_date=2026-01-01/x.csv",
                    type=FileType.File,
                    mtime=now,
                ),
                FileInfo(
                    f"{base}/event_date=2026-01-01/_temporary/y.parquet",
                    type=FileType.File,
                    mtime=now,
                ),
            ],
            metadata={
                f"{base}/_spark_metadata/0": spark_metadata(
                    "s3a://de-practicum/streaming/orders_raw/event_date=2026-01-01/committed.parquet"
                )
            },
        )
        result = w.list_new_files(fs, set())
        assert [i.path for i in result] == [committed_path]

    def test_committed_file_is_eligible_regardless_of_mtime(self) -> None:
        base = "de-practicum/streaming/orders_raw"
        old_path = f"{base}/event_date=2026-01-01/old.parquet"
        fs = FakeFS(
            [FileInfo(old_path, type=FileType.File, mtime=datetime.now(timezone.utc))],
            metadata={
                f"{base}/_spark_metadata/7": spark_metadata(
                    "s3a://de-practicum/streaming/orders_raw/event_date=2026-01-01/old.parquet"
                )
            },
        )
        result = w.list_new_files(fs, set())
        assert [i.path for i in result] == [old_path]

    def test_repeated_discovery_is_suppressed_by_done_paths(self) -> None:
        base = "de-practicum/streaming/orders_raw"
        path = f"{base}/event_date=2026-01-01/part.parquet"
        fs = FakeFS(
            [FileInfo(path, type=FileType.File)],
            metadata={
                f"{base}/_spark_metadata/0": spark_metadata(
                    "s3a://de-practicum/streaming/orders_raw/event_date=2026-01-01/part.parquet"
                )
            },
        )
        assert [item.path for item in w.list_new_files(fs, set())] == [path]
        assert w.list_new_files(fs, {path}) == []

    def test_invalid_commit_log_fails_closed(self) -> None:
        base = "de-practicum/streaming/orders_raw"
        fs = FakeFS(
            [],
            metadata={f"{base}/_spark_metadata/0": "not-a-spark-log\n"},
        )
        with pytest.raises(ValueError, match="invalid Spark commit log"):
            w.committed_landing_paths(fs)


class TestCommittedLoadIds:
    def test_reads_snapshot_summaries(self) -> None:
        table = FakeTable(
            [
                FakeSnap({"load-id": "abc"}),
                FakeSnap({"load-id": "def"}),
                FakeSnap({"other": "x"}),
                FakeSnap(None),
            ]
        )
        assert w.committed_load_ids(FakeCatalog(table)) == {"abc", "def"}

    def test_missing_table_returns_empty(self) -> None:
        assert w.committed_load_ids(FakeCatalog(None)) == set()


class TestRecoverPending:
    def test_committed_loads_marked_done(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
        table = FakeTable([FakeSnap({"load-id": "abc"})])
        done, pending = set(), {"abc": ["f1", "f2"], "zzz": ["f3"]}
        w.recover_pending(done, pending, FakeCatalog(table))
        assert done == {"f1", "f2"}
        assert pending == {"zzz": ["f3"]}
        saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert sorted(saved["done"]) == ["f1", "f2"]

    def test_uncommitted_stays_pending(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
        table = FakeTable([])
        done, pending = set(), {"zzz": ["f3"]}
        w.recover_pending(done, pending, FakeCatalog(table))
        assert done == set()
        assert pending == {"zzz": ["f3"]}

    def test_empty_pending_is_noop(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
        catalog = FakeCatalog(None)
        w.recover_pending(set(), {}, catalog)
        assert catalog.table is None


class EnsureCatalog:
    def __init__(self) -> None:
        self.namespaces: list[str] = []
        self.tables: dict[str, object] = {}

    def create_namespace_if_not_exists(self, namespace: str) -> None:
        self.namespaces.append(namespace)

    def load_table(self, identifier: str) -> object:
        if identifier not in self.tables:
            raise NoSuchTableError(identifier)
        return self.tables[identifier]

    def create_table(self, identifier: str, **kwargs) -> object:
        self.tables[identifier] = object()
        return self.tables[identifier]


class TestFsCatalogAndBatch:
    def test_get_fs_returns_s3_filesystem(self, monkeypatch) -> None:
        from pyarrow.fs import S3FileSystem

        monkeypatch.setattr(w, "ACCESS_KEY", "minio")
        monkeypatch.setattr(w, "SECRET_KEY", "minio123")
        assert isinstance(w.get_fs(), S3FileSystem)

    def test_get_catalog_returns_rest_catalog(self, monkeypatch) -> None:
        class FakeRestCatalog:
            def __init__(self, name: str, **kwargs) -> None:
                self.name = name
                self.kwargs = kwargs

        monkeypatch.setattr(w, "RestCatalog", FakeRestCatalog)
        cat = w.get_catalog()
        assert isinstance(cat, FakeRestCatalog)
        assert cat.name == "default"
        assert cat.kwargs["s3.endpoint"] == w.S3_ENDPOINT

    def test_ensure_table_existing_is_noop(self) -> None:
        catalog = EnsureCatalog()
        catalog.tables["bronze.orders"] = object()
        w.ensure_table(catalog)
        assert catalog.namespaces == ["bronze"]
        assert len(catalog.tables) == 1

    def test_ensure_table_creates_when_missing(self) -> None:
        catalog = EnsureCatalog()
        w.ensure_table(catalog)
        assert catalog.namespaces == ["bronze"]
        assert "bronze.orders" in catalog.tables

    def test_read_batch_reads_hive_partitioned_parquet(self, tmp_path) -> None:
        import pyarrow.parquet as pq
        from pyarrow.fs import LocalFileSystem

        partition_dir = tmp_path / "data" / "event_date=2026-01-01"
        partition_dir.mkdir(parents=True)
        ts = datetime(2026, 1, 1, 12, 0, 0)
        pq.write_table(
            pa.table(
                {
                    "order_id": ["a", "b"],
                    "amount": pa.array([10.0, 20.0], type=pa.float64()),
                    "status": ["paid", "paid"],
                    "event_time": pa.array([ts, ts], type=pa.timestamp("us")),
                    "kafka_offset": pa.array([1, 2], type=pa.int64()),
                    "business_version": pa.array([1, 1], type=pa.int64()),
                }
            ),
            partition_dir / "part-00000.parquet",
        )
        result = w.read_batch(
            LocalFileSystem(),
            [SimpleNamespace(path=str(partition_dir / "part-00000.parquet"))],
        )
        assert result.num_rows == 2
        assert "event_date" in result.column_names
        assert result.column_names.count("business_version") == 1
        assert result["business_version"].to_pylist() == [1, 1]
        assert pa.types.is_date32(result.schema.field("event_date").type)


def _main_setup(monkeypatch, tmp_path, table: FakeTable | None = None):
    monkeypatch.setattr(w, "Metrics", lambda: FakeMetrics())
    monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(w, "POLL_INTERVAL", 0)
    monkeypatch.setattr(w, "MAX_APPEND_ATTEMPTS", 5)
    sleep_calls: list[float] = []
    monkeypatch.setattr(w.time, "sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(w, "get_fs", lambda: object())
    monkeypatch.setattr(w, "get_catalog", lambda: FakeCatalog(table or FakeTable()))
    monkeypatch.setattr(w, "publish_outbox", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        w, "read_batch", lambda fs, files: pa.table({"order_id": ["x"]})
    )
    monkeypatch.setattr(w, "ensure_table", lambda catalog: None)
    calls = {"n": 0}
    file = settled_file("a.parquet", 60)

    def fake_list_new_files(fs, done):
        calls["n"] += 1
        if calls["n"] == 1:
            return [file]
        raise SystemExit()

    monkeypatch.setattr(w, "list_new_files", fake_list_new_files)
    return file, sleep_calls, table


class TestMain:
    def test_success_iteration(self, monkeypatch, tmp_path) -> None:
        table = FakeTable()
        _, _, table = _main_setup(monkeypatch, tmp_path, table)
        with pytest.raises(SystemExit):
            w.main()
        assert len(table.append_calls) == 1
        assert w.LOAD_ID_KEY in table.append_calls[0]
        state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert state["done"] == ["a.parquet"]
        assert state["pending"] == {}

    def test_commit_conflict_retries_then_succeeds(self, monkeypatch, tmp_path) -> None:
        table = FakeTable()
        table.append_failures = 1
        _, sleep_calls, table = _main_setup(monkeypatch, tmp_path, table)
        with pytest.raises(SystemExit):
            w.main()
        assert len(table.append_calls) == 2
        assert sleep_calls[0] == 1.0

    def test_error_path_cleans_pending(self, monkeypatch, tmp_path) -> None:
        table = FakeTable()
        table.append_failures = 10**6
        _main_setup(monkeypatch, tmp_path, table)
        with pytest.raises(SystemExit):
            w.main()
        state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert state["done"] == []
        assert state["pending"] == {}

    def test_error_path_marks_committed_load_done(self, monkeypatch, tmp_path) -> None:
        fixed_load = uuid.UUID(int=0).hex
        monkeypatch.setattr(w.uuid, "uuid4", lambda: uuid.UUID(int=0))
        table = FakeTable([FakeSnap({"load-id": fixed_load})])
        table.append_failures = 10**6
        _main_setup(monkeypatch, tmp_path, table)
        with pytest.raises(SystemExit):
            w.main()
        state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert state["done"] == ["a.parquet"]
        assert state["pending"] == {}

    def test_simulated_crash_before_commit(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(w, "SIMULATE_CRASH_BEFORE_COMMIT", True)
        monkeypatch.setattr(
            w.os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code))
        )
        _main_setup(monkeypatch, tmp_path, FakeTable())
        with pytest.raises(SystemExit) as exc:
            w.main()
        assert exc.value.code == 2

    def test_simulated_crash_after_commit_keeps_pending(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(w, "SIMULATE_CRASH_AFTER_COMMIT", True)
        monkeypatch.setattr(
            w.os, "_exit", lambda code: (_ for _ in ()).throw(SystemExit(code))
        )
        _main_setup(monkeypatch, tmp_path, FakeTable())
        with pytest.raises(SystemExit) as exc:
            w.main()
        assert exc.value.code == 3
        state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert state["done"] == []
        assert len(state["pending"]) == 1
