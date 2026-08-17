"""Reusable in-memory test doubles for the lakehouse catalog and metrics sink.

These are plain importable objects rather than fixtures so unit, BDD and
integration tests can share one model of the catalog. They mirror the slice of
PyIceberg the medallion actually uses: scan the current Arrow table, overwrite
it, and create tables/namespaces on demand.

The writer exercises a different slice — snapshot summaries, appends and commit
conflicts — and keeps its own doubles in ``tests/test_writer.py`` until a second
consumer needs them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pyarrow as pa
from pyiceberg.exceptions import NoSuchTableError


class FakeScan:
    def __init__(self, df: pa.Table) -> None:
        self.df = df

    def to_arrow(self) -> pa.Table:
        return self.df


class FakeTable:
    def __init__(
        self, df: pa.Table | None = None, *, snapshot_history: int = 0
    ) -> None:
        self.df = df
        # Rewrite count, so a specification can assert that a table was left
        # untouched — not merely that its contents happen to look the same.
        self.overwrite_calls = 0
        # Snapshot identity and the properties each rewrite carried. A one-shot
        # migration has to be auditable after the fact, so "which snapshot did
        # this write produce, and what provenance did it record" is part of the
        # contract, not an implementation detail.
        self.snapshots: list[SimpleNamespace] = []
        self.snapshot_properties: list[dict] = []
        for _ in range(snapshot_history):
            self.add_snapshot()

    @property
    def num_rows(self) -> int:
        return 0 if self.df is None else self.df.num_rows

    def add_snapshot(self, **summary: str) -> SimpleNamespace:
        snapshot = SimpleNamespace(
            snapshot_id=len(self.snapshots) + 1,
            summary=SimpleNamespace(additional_properties=dict(summary)),
        )
        self.snapshots.append(snapshot)
        return snapshot

    def current_snapshot(self) -> SimpleNamespace | None:
        return self.snapshots[-1] if self.snapshots else None

    def scan(self, row_filter=None) -> FakeScan:
        return FakeScan(self.df)

    def overwrite(self, df: pa.Table, **kwargs) -> None:
        self.df = df
        self.overwrite_calls += 1
        properties = dict(kwargs.get("snapshot_properties") or {})
        self.snapshot_properties.append(properties)
        self.add_snapshot(**properties)


class FakeCatalog:
    def __init__(self, tables: dict[str, FakeTable] | None = None) -> None:
        self.tables = tables or {}

    def load_table(self, identifier: str) -> FakeTable:
        if identifier not in self.tables:
            raise NoSuchTableError(f"no table {identifier}")
        return self.tables[identifier]

    def create_namespace_if_not_exists(self, namespace: str) -> None:
        pass

    def create_table(self, identifier: str, **kwargs) -> FakeTable:
        table = FakeTable(None)
        self.tables[identifier] = table
        return table


class FakeMetrics:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)
