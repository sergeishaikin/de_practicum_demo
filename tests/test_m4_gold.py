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
    def __init__(self, arrow_table: pa.Table | None = None) -> None:
        self.df = arrow_table
        self.overwrite_calls = 0

    def scan(self, row_filter=None):
        return SimpleNamespace(
            to_arrow=lambda: self.df if self.df is not None else table([])
        )

    def overwrite(self, arrow_table, **kwargs) -> None:
        self.df = arrow_table
        self.overwrite_calls += 1


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
    monkeypatch.setattr(m, "run_b2", lambda *args: None)
    monkeypatch.setattr(m, "GOLD_SOURCE", gold_source)
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", shadow)
    return catalog, persisted_silver, gold, FakeMetrics()


def test_persisted_silver_gold_does_not_rebuild_silver_from_bronze(monkeypatch) -> None:
    catalog, persisted_silver, gold, metrics = setup_gold_run(
        monkeypatch, gold_source="persisted_silver"
    )
    monkeypatch.setattr(
        m,
        "build_silver",
        lambda _: pytest.fail("persisted-Silver Gold must not rebuild Silver"),
    )

    m.run(catalog, metrics, "b2")

    assert gold.df is not None
    assert gold.overwrite_calls == 1
    assert persisted_silver.overwrite_calls == 0
    assert metrics.records[-1]["status"] == "success"
    assert metrics.records[-1]["shadow_comparisons"] == 0


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
