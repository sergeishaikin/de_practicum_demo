"""pytest-bdd steps for the data quality enforcement contract.

Steps bind to the production callables directly: ``run_quality_checks`` for the
classification rules, and ``run`` for the mode behavior. The catalog and metrics
sink are the same in-memory doubles the medallion unit tests use, so the whole
feature stays T1 — no stack, default fast suite.
"""

from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa
import pytest
from pyiceberg.exceptions import NoSuchTableError
from pytest_bdd import given, parsers, scenarios, then, when

from medallion import iceberg_medallion as m

scenarios("data_quality_modes.feature")

pytestmark = [pytest.mark.bdd]

TS = datetime(2026, 8, 8, 12, 0, 0)
EVENT_DATE = date(2026, 8, 8)

SILVER_ID = "silver.orders_clean"
GOLD_ID = "gold.orders_daily_metrics"

# One defective field per case. Everything else stays well-formed so the
# scenario proves the rule under test and nothing else.
DEFECTS: dict[str, dict] = {
    "a missing order id": {"order_id": None},
    "a missing amount": {"amount": None},
    "an amount of zero": {"amount": 0.0},
    "a negative amount": {"amount": -1.0},
    "a missing country": {"country": None},
    "an unknown status": {"status": "teleported"},
    "a missing event time": {"event_time": None},
}


class FakeScan:
    def __init__(self, df: pa.Table) -> None:
        self.df = df

    def to_arrow(self) -> pa.Table:
        return self.df


class FakeTable:
    def __init__(self, df: pa.Table | None = None) -> None:
        self.df = df

    @property
    def num_rows(self) -> int:
        return 0 if self.df is None else self.df.num_rows

    def scan(self) -> FakeScan:
        return FakeScan(self.df)

    def overwrite(self, df: pa.Table) -> None:
        self.df = df


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


def _order(**overrides) -> dict:
    order = {
        "order_id": "order-1",
        "customer": "customer-1",
        "amount": 10.0,
        "country": "US",
        "status": "paid",
        "event_time": TS,
    }
    order.update(overrides)
    return order


def _bronze(orders: list[dict], *, drop: str | None = None) -> pa.Table:
    columns = {
        "order_id": pa.array([o["order_id"] for o in orders], type=pa.string()),
        "customer": pa.array([o["customer"] for o in orders], type=pa.string()),
        "amount": pa.array([o["amount"] for o in orders], type=pa.float64()),
        "country": pa.array([o["country"] for o in orders], type=pa.string()),
        "status": pa.array([o["status"] for o in orders], type=pa.string()),
        "event_time": pa.array(
            [o["event_time"] for o in orders], type=pa.timestamp("us")
        ),
        "kafka_timestamp": pa.array([TS] * len(orders), type=pa.timestamp("us")),
        "kafka_partition": pa.array([0] * len(orders), type=pa.int32()),
        "kafka_offset": pa.array(list(range(len(orders))), type=pa.int64()),
        "event_date": pa.array([EVENT_DATE] * len(orders), type=pa.date32()),
    }
    if drop is not None:
        del columns[drop]
    return pa.table(columns)


@pytest.fixture
def context() -> dict:
    return {}


# --- Given -----------------------------------------------------------------


@given("a batch of well-formed orders")
def clean_batch(context: dict) -> None:
    context["bronze"] = _bronze(
        [_order(order_id="order-1"), _order(order_id="order-2", amount=20.0)]
    )


@given(parsers.parse("a batch containing an order with {defect}"))
def defective_batch(context: dict, defect: str) -> None:
    assert defect in DEFECTS, f"unknown defect {defect!r}"
    defective = {"order_id": "order-1", **DEFECTS[defect]}
    context["bronze"] = _bronze([_order(**defective), _order(order_id="order-2")])


@given("a batch that does not carry the country field")
def batch_without_country(context: dict) -> None:
    context["bronze"] = _bronze([_order()], drop="country")


# --- When ------------------------------------------------------------------


@when("quality validation runs")
def validate(context: dict) -> None:
    context["violations"] = m.run_quality_checks(context["bronze"])


@when(parsers.parse("the medallion cycle runs in {mode} mode"))
def run_cycle(context: dict, mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    assert mode in ("strict", "permissive"), f"unknown mode {mode!r}"
    monkeypatch.setattr(m, "FAIL_ON_VIOLATIONS", mode == "strict")
    catalog = FakeCatalog({"bronze.orders": FakeTable(context["bronze"])})
    metrics = FakeMetrics()
    m.run(catalog, metrics)
    context["catalog"] = catalog
    context["metrics"] = metrics


# --- Then ------------------------------------------------------------------


@then("no quality violations are reported")
def no_violations(context: dict) -> None:
    assert context["violations"] == {}


@then(parsers.parse("exactly {count:d} quality violation is reported"))
def violation_count(context: dict, count: int) -> None:
    assert (
        sum(context["violations"].values()) == count
    ), f"reported violations: {context['violations']}"


@then("the curated order state is published")
def state_published(context: dict) -> None:
    tables = context["catalog"].tables
    assert SILVER_ID in tables, "silver was never created"
    assert GOLD_ID in tables, "gold was never created"
    assert tables[SILVER_ID].num_rows > 0


@then("nothing is published")
def nothing_published(context: dict) -> None:
    # Fail-closed: the abort must happen before curation, so no downstream
    # table may exist at all.
    tables = context["catalog"].tables
    assert SILVER_ID not in tables, "silver was published despite a strict violation"
    assert GOLD_ID not in tables, "gold was published despite a strict violation"


@then(parsers.parse("the run is recorded as {status}"))
def run_status(context: dict, status: str) -> None:
    expected = {"successful": "success", "failed": "failed"}[status]
    records = context["metrics"].records
    assert records, "no operational evidence was recorded"
    assert records[-1]["status"] == expected
    assert records[-1]["source"] == "medallion"


@then(parsers.parse("the recorded violation count is {count:d}"))
def recorded_violations(context: dict, count: int) -> None:
    assert context["metrics"].records[-1]["quality_violations"] == count
