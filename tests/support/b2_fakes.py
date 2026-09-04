"""In-memory doubles for the B2 slice: object storage plus a snapshotting table.

These model the part of PyIceberg and S3 that incremental B2 processing and the
S1.2 reconciliation actually touch — a row filter pushed into a scan, an
``overwrite`` that replaces matched keys and appends a snapshot summary, and an
object store that ``list_bronze_work`` / ``load_progress`` / the completion
ledger can be driven against for real.

They live here rather than in ``tests/support/fakes.py`` because that module
models the *legacy* medallion slice, whose ``FakeTable.overwrite`` takes no
partition filter. Keeping both is deliberate: a single conflated double would
have to accept either signature and would stop proving which path ran.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pyarrow as pa
from pyarrow.fs import FileInfo, FileType

from medallion import iceberg_medallion as m

__all__ = [
    "FakeCatalog",
    "FakeFS",
    "FakeIcebergTable",
    "FakeScan",
    "OutputStream",
    "predicate_values",
    "rows_to_arrow",
]

# 2026-01-01T00:00:00Z, so generated snapshot timestamps are stable and ordered.
BASE_TIMESTAMP_MS = 1_767_225_600_000


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

    def open_input_stream(self, path: str):
        # Production reads small JSON objects sequentially, never by an
        # advertised size. The double has to offer the same API or it stops
        # exercising the code that runs. Both forms return the stored bytes here
        # because the double has no notion of a read spanning an overwrite -
        # that is what tests/integration/test_progress_read_under_shrink.py is
        # for, against a real object store.
        return self.open_input_file(path)

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
        if self.row_filter is not None:
            values = predicate_values(self.row_filter)
            rows = [item for item in rows if item["order_id"] in values]
        return rows_to_arrow(rows)

    def plan_files(self):
        values = predicate_values(self.row_filter)
        if not any(item["order_id"] in values for item in self.table.rows):
            return iter(())
        return iter(
            [
                SimpleNamespace(
                    file=SimpleNamespace(file_size_in_bytes=self.table.file_size)
                )
            ]
        )


class FakeIcebergTable:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.file_size = len(self.rows) * 100
        self.metadata = SimpleNamespace(snapshots=[])

    def add_snapshot(self, **summary: str) -> SimpleNamespace:
        """Seed a snapshot summary without writing rows.

        Snapshot *history* is evidence in its own right for S1.2: a load-id
        append, a migration marker, or a committed Silver work id all have to be
        readable without the rows that produced them still being reproducible.
        """

        return self._append_snapshot(summary)

    def _append_snapshot(self, summary: dict) -> SimpleNamespace:
        sequence = len(self.metadata.snapshots) + 1
        snapshot = SimpleNamespace(
            snapshot_id=sequence,
            timestamp_ms=BASE_TIMESTAMP_MS + sequence * 1000,
            summary=SimpleNamespace(additional_properties=dict(summary)),
        )
        self.metadata.snapshots.append(snapshot)
        return snapshot

    def scan(self, row_filter=None) -> FakeScan:
        return FakeScan(self, row_filter)

    def overwrite(
        self, arrow_table, overwrite_filter, snapshot_properties=None
    ) -> None:
        values = predicate_values(overwrite_filter)
        removed_files = int(any(item["order_id"] in values for item in self.rows))
        removed_bytes = self.file_size if removed_files else 0
        self.rows = [item for item in self.rows if item["order_id"] not in values]
        self.rows.extend(arrow_table.to_pylist())
        self.file_size = arrow_table.nbytes
        self._append_snapshot(
            {
                "deleted-data-files": str(removed_files),
                "added-data-files": "1",
                "removed-files-size": str(removed_bytes),
                "added-files-size": str(self.file_size),
                **(snapshot_properties or {}),
            }
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
