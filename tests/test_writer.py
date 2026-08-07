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
    def __init__(self, props: dict | None = None) -> None:
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
    def __init__(self, infos: list[FileInfo]) -> None:
        self.infos = infos

    def get_file_info(self, selector) -> list[FileInfo]:
        return self.infos


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


class TestIsSettled:
    def test_respects_settle_seconds(self, monkeypatch) -> None:
        monkeypatch.setattr(w, "SETTLE_SECONDS", 5)
        now = datetime.now(timezone.utc)
        assert w.is_settled(FileInfo("x", mtime=now - timedelta(seconds=10)))
        assert not w.is_settled(FileInfo("x", mtime=now - timedelta(seconds=1)))

    def test_naive_mtime_treated_as_utc(self, monkeypatch) -> None:
        monkeypatch.setattr(w, "SETTLE_SECONDS", 5)
        now = datetime.now(timezone.utc)
        naive = (now - timedelta(seconds=10)).replace(tzinfo=None)
        assert w.is_settled(FileInfo("x", mtime=naive))


class TestListNewFiles:
    def test_filters_and_sorts(self, monkeypatch) -> None:
        monkeypatch.setattr(w, "SETTLE_SECONDS", 5)
        now = datetime.now(timezone.utc)
        fs = FakeFS(
            [
                FileInfo("old.parquet", type=FileType.File, mtime=now - timedelta(seconds=60)),
                FileInfo("new.parquet", type=FileType.File, mtime=now - timedelta(seconds=6)),
                FileInfo("dir", type=FileType.Directory, mtime=now),
                FileInfo("x.csv", type=FileType.File, mtime=now - timedelta(seconds=60)),
                FileInfo(
                    "c/_temporary/y.parquet",
                    type=FileType.File,
                    mtime=now - timedelta(seconds=60),
                ),
                FileInfo("done.parquet", type=FileType.File, mtime=now - timedelta(seconds=60)),
                FileInfo("recent.parquet", type=FileType.File, mtime=now - timedelta(seconds=1)),
            ]
        )
        result = w.list_new_files(fs, {"done.parquet"})
        assert [i.path for i in result] == ["old.parquet", "new.parquet"]

    def test_sort_by_mtime_ascending(self, monkeypatch) -> None:
        monkeypatch.setattr(w, "SETTLE_SECONDS", 0)
        now = datetime.now(timezone.utc)
        fs = FakeFS(
            [
                FileInfo("b.parquet", type=FileType.File, mtime=now - timedelta(seconds=2)),
                FileInfo("a.parquet", type=FileType.File, mtime=now - timedelta(seconds=6)),
            ]
        )
        result = w.list_new_files(fs, set())
        assert [i.path for i in result] == ["a.parquet", "b.parquet"]


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


def _main_setup(monkeypatch, tmp_path, table: FakeTable | None = None):
    monkeypatch.setattr(w, "Metrics", lambda: FakeMetrics())
    monkeypatch.setattr(w, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(w, "POLL_INTERVAL", 0)
    monkeypatch.setattr(w, "MAX_APPEND_ATTEMPTS", 5)
    sleep_calls: list[float] = []
    monkeypatch.setattr(w.time, "sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(w, "get_fs", lambda: object())
    monkeypatch.setattr(w, "get_catalog", lambda: FakeCatalog(table or FakeTable()))
    monkeypatch.setattr(w, "read_batch", lambda fs, files: pa.table({"order_id": ["x"]}))
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
        fixed_load = "a" * 32
        monkeypatch.setattr(w.uuid, "uuid4", lambda: uuid.UUID(int=0))
        table = FakeTable([FakeSnap({"load-id": fixed_load})])
        _main_setup(monkeypatch, tmp_path, table)
        with pytest.raises(SystemExit):
            w.main()
        state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert state["done"] == ["a.parquet"]
        assert state["pending"] == {}
