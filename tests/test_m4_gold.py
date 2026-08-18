from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pyarrow as pa
import pytest

from medallion import iceberg_medallion as m

TS = datetime(2026, 1, 1, 12, 0, 0)


def row(order_id: str, version: int, *, amount: float = 10.0, offset: int = 1) -> dict:
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": TS,
        "kafka_timestamp": TS,
        "kafka_partition": 0,
        "kafka_offset": offset,
        "event_date": date(2026, 1, 1),
        "business_version": version,
    }


def table(rows: list[dict]) -> pa.Table:
    return m._rows_to_silver(rows)


def test_shadow_comparison_is_order_and_transport_independent() -> None:
    legacy = table([row("b", 2, offset=1), row("a", 1, offset=2)])
    b2 = table([row("a", 1, offset=999), row("b", 2, offset=888)])
    result = m.compare_business_state(legacy, b2)
    assert result["equal"]
    assert result["excluded_columns"] == [
        "kafka_timestamp",
        "kafka_partition",
        "kafka_offset",
    ]


def test_shadow_duplicate_resolution_is_independent_of_physical_row_order() -> None:
    first = table([row("a", 2, amount=20), row("a", 1, amount=10)])
    second = table([row("a", 1, amount=10), row("a", 2, amount=20)])

    result_first = m.compare_business_state(first, table([row("a", 1, amount=10)]))
    result_second = m.compare_business_state(second, table([row("a", 1, amount=10)]))

    assert result_first == result_second
    assert result_first["mismatches"][0]["mismatch_type"] == "duplicate_business_key"


@pytest.mark.parametrize(
    ("legacy", "b2", "mismatch_type"),
    [
        ([row("a", 1)], [row("b", 1)], "missing_in_persisted_b2"),
        ([row("b", 1)], [row("a", 1), row("b", 1)], "missing_in_legacy"),
        ([row("a", 1), row("a", 1)], [row("a", 1)], "duplicate_business_key"),
        ([row("a", 1)], [row("a", 2)], "business_version_mismatch"),
        ([row("a", 1, amount=10)], [row("a", 1, amount=11)], "payload_mismatch"),
    ],
)
def test_shadow_comparison_reports_deterministic_mismatch(
    legacy: list[dict], b2: list[dict], mismatch_type: str
) -> None:
    result = m.compare_business_state(table(legacy), table(b2))
    assert not result["equal"]
    assert result["mismatches"][0]["mismatch_type"] == mismatch_type
    assert result["mismatches"][0]["order_id"] == "a"


class FakeTable:
    """Local double, mirroring ``tests/support/fakes.py:FakeTable`` field-for-field.

    Kept separate deliberately rather than reusing the shared double: that one's
    ``scan()`` yields ``None`` for an empty table, while several Gold tests in
    this module depend on an empty *typed* Arrow table instead. Converging them
    would mean changing the shared double's empty-scan semantics for every other
    consumer, so the duplication is a decision, not an oversight.
    """

    def __init__(self, arrow_table: pa.Table | None = None) -> None:
        self.df = arrow_table
        self.overwrite_calls = 0
        self.snapshots: list = []
        self.snapshot_properties: list[dict] = []

    def scan(self, row_filter=None):
        return SimpleNamespace(
            to_arrow=lambda: self.df if self.df is not None else table([])
        )

    def add_snapshot(self, **summary):
        snapshot = SimpleNamespace(
            snapshot_id=len(self.snapshots) + 1,
            summary=SimpleNamespace(additional_properties=dict(summary)),
        )
        self.snapshots.append(snapshot)
        return snapshot

    def current_snapshot(self):
        return self.snapshots[-1] if self.snapshots else None

    def overwrite(self, arrow_table, **kwargs) -> None:
        self.df = arrow_table
        self.overwrite_calls += 1
        properties = dict(kwargs.get("snapshot_properties") or {})
        self.snapshot_properties.append(properties)
        self.add_snapshot(**properties)


class FakeCatalog:
    def __init__(self, tables: dict[str, FakeTable]) -> None:
        self.tables = tables

    def load_table(self, identifier: str) -> FakeTable:
        return self.tables[identifier]


class FakeMetrics:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


def setup_gold_run(monkeypatch, *, gold_source: str, shadow: bool = False):
    bronze = FakeTable(table([row("a", 1)]))
    persisted_silver = FakeTable(table([row("a", 5, amount=50)]))
    gold = FakeTable()
    catalog = FakeCatalog(
        {
            "bronze.orders": bronze,
            "silver.orders_clean": persisted_silver,
            "gold.orders_daily_metrics": gold,
        }
    )
    monkeypatch.setattr(m, "ensure_table", lambda *args: None)
    # Keyword-tolerant: plan 04-03 calls run_b2(..., cycle_id=...), and a bare
    # *args lambda raises TypeError on any keyword argument.
    monkeypatch.setattr(m, "run_b2", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "GOLD_SOURCE", gold_source)
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", shadow)
    return catalog, persisted_silver, gold, FakeMetrics()


def test_cutover_gold_is_served_from_persisted_silver(monkeypatch) -> None:
    # Scoped to the accepted cutover state (b2 / persisted_silver / shadow on),
    # which is the only accepted configuration that reads persisted Silver.
    #
    # Shadow validation needs the legacy projection, so a rebuild *does* happen
    # here — an earlier version of this test asserted the opposite, but reached
    # that state with shadow off, a combination the rollout matrix forbids and
    # main() refuses to boot into. What the cutover contract actually requires is
    # that Gold is fed from persisted Silver rather than from the rebuild, and
    # that the Gold cycle never rewrites persisted Silver.
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])

    gold_inputs = []
    real_build_gold = m.build_gold

    def capture_gold_input(df):
        gold_inputs.append(df)
        return real_build_gold(df)

    monkeypatch.setattr(m, "build_gold", capture_gold_input)

    m.run(catalog, metrics, "b2")

    # Identity, not equality: shadow compare forces the two projections to agree,
    # so only object identity can tell which one reached Gold.
    assert gold_inputs, "Gold was never built"
    assert gold_inputs[0] is persisted_silver.df
    assert gold.df is not None
    assert gold.overwrite_calls == 1
    assert persisted_silver.overwrite_calls == 0
    assert metrics.records[-1]["status"] == "success"
    assert metrics.records[-1]["shadow_comparisons"] == 1


def test_shadow_mismatch_fails_closed_before_gold_write(monkeypatch) -> None:
    catalog, _, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="legacy", shadow=True
    )
    with pytest.raises(ValueError, match="Shadow comparison failed"):
        m.run(catalog, metrics, "b2")
    assert gold.overwrite_calls == 0
    assert metrics.records[-1]["status"] == "shadow_failed"
    assert metrics.records[-1]["shadow_comparisons"] == 1
    assert metrics.records[-1]["shadow_mismatches"] == 1


def test_shadow_uses_bronze_boundary_pinned_before_b2_runs(monkeypatch) -> None:
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="legacy", shadow=True
    )
    persisted_silver.df = table([row("a", 1)])

    def mutate_bronze_after_boundary(*args) -> None:
        catalog.tables["bronze.orders"].df = table([row("a", 2)])

    monkeypatch.setattr(m, "run_b2", mutate_bronze_after_boundary)

    m.run(catalog, metrics, "b2")

    assert gold.overwrite_calls == 1
    assert metrics.records[-1]["status"] == "success"


def test_switching_gold_source_does_not_mutate_persisted_silver(monkeypatch) -> None:
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver"
    )
    m.run(catalog, metrics, "b2")
    persisted_snapshot = persisted_silver.overwrite_calls

    monkeypatch.setattr(m, "GOLD_SOURCE", "legacy")
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", False)
    m.run(catalog, metrics, "b2")

    assert persisted_silver.overwrite_calls == persisted_snapshot
    assert gold.overwrite_calls == 2


def test_fake_table_records_snapshot_properties_and_advances_current() -> None:
    """The double must express what a Gold write carried and which snapshot won."""

    gold = FakeTable()
    gold.overwrite(table([]), snapshot_properties={"source-silver-snapshot-id": "11"})
    gold.overwrite(table([]), snapshot_properties={"source-silver-snapshot-id": "22"})

    assert gold.current_snapshot().snapshot_id == 2
    assert len(gold.snapshot_properties) == 2
    assert gold.snapshot_properties[-1] == {"source-silver-snapshot-id": "22"}


def test_fake_table_current_snapshot_ignores_older_provenance() -> None:
    """A bare newer snapshot must hide an older property-bearing one.

    This is the fixture the "read provenance from current_snapshot() only" rule
    needs: a Trino maintenance rewrite can leave a newer snapshot with no
    provenance property, and trusting an older one would silently certify Gold
    against a Silver snapshot that no longer produced it.
    """

    gold = FakeTable()
    gold.add_snapshot(**{"source-silver-snapshot-id": "11"})
    gold.add_snapshot()

    assert gold.current_snapshot().summary.additional_properties == {}
