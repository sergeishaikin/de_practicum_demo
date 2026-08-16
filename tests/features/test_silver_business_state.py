"""pytest-bdd steps for the Silver current-business-state contract.

The steps bind to the same production callables the medallion uses:
``resolve_against_current`` (imported by ``medallion.iceberg_medallion``) for the
incremental path, and ``build_silver`` for the legacy rebuild path. Both must
obey the identical domain rule, so the scenarios never name which one runs.
"""

from __future__ import annotations

import copy
from datetime import date, datetime

import pyarrow as pa
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from b2_spike import resolve_against_current
from medallion import iceberg_medallion as m

scenarios("silver_business_state.feature")

pytestmark = [pytest.mark.bdd]

TS = datetime(2026, 8, 8, 12, 0, 0)
DEFAULT_DAY = date(2026, 8, 8)


def _row(
    order_id: str,
    version: int,
    amount: float,
    *,
    day: date = DEFAULT_DAY,
    offset: int = 0,
) -> dict:
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}",
        "amount": float(amount),
        "country": "US",
        "status": "paid",
        "event_time": TS,
        "kafka_timestamp": TS,
        "kafka_partition": 0,
        "kafka_offset": offset,
        "event_date": day,
        "business_version": version,
    }


def _bronze_table(rows: list[dict]) -> pa.Table:
    return pa.table(
        {
            "order_id": pa.array([r["order_id"] for r in rows], type=pa.string()),
            "customer": pa.array([r["customer"] for r in rows], type=pa.string()),
            "amount": pa.array([r["amount"] for r in rows], type=pa.float64()),
            "country": pa.array([r["country"] for r in rows], type=pa.string()),
            "status": pa.array([r["status"] for r in rows], type=pa.string()),
            "event_time": pa.array(
                [r["event_time"] for r in rows], type=pa.timestamp("us")
            ),
            "kafka_timestamp": pa.array(
                [r["kafka_timestamp"] for r in rows], type=pa.timestamp("us")
            ),
            "kafka_partition": pa.array(
                [r["kafka_partition"] for r in rows], type=pa.int32()
            ),
            "kafka_offset": pa.array(
                [r["kafka_offset"] for r in rows], type=pa.int64()
            ),
            "event_date": pa.array([r["event_date"] for r in rows], type=pa.date32()),
            "business_version": pa.array(
                [r["business_version"] for r in rows], type=pa.int64()
            ),
        }
    )


@pytest.fixture
def context() -> dict:
    return {"current": [], "incoming": [], "observed": [], "error": None}


# --- Given -----------------------------------------------------------------


@given("no current order state")
def no_current_state(context: dict) -> None:
    context["current"] = []


@given(
    parsers.parse(
        'a current order "{order}" at business version {version:d} '
        "with amount {amount:d}"
    )
)
def current_order(context: dict, order: str, version: int, amount: int) -> None:
    context["current"].append(_row(order, version, amount))


@given(
    parsers.parse(
        'an incoming order "{order}" at business version {version:d} '
        "with amount {amount:d}"
    )
)
def incoming_order(context: dict, order: str, version: int, amount: int) -> None:
    context["incoming"].append(_row(order, version, amount))


@given(
    parsers.parse(
        'an observed order "{order}" at business version {version:d} '
        "with amount {amount:d} at transport offset {offset:d}"
    )
)
def observed_order(
    context: dict, order: str, version: int, amount: int, offset: int
) -> None:
    context["observed"].append(_row(order, version, amount, offset=offset))


@given(
    parsers.parse(
        'an observed order "{order}" at business version {version:d} '
        "with amount {amount:d} on {day} at transport offset {offset:d}"
    )
)
def observed_order_on_day(
    context: dict, order: str, version: int, amount: int, day: str, offset: int
) -> None:
    context["observed"].append(
        _row(order, version, amount, day=date.fromisoformat(day), offset=offset)
    )


# --- When ------------------------------------------------------------------


@when("the incoming observations are resolved against current state")
def resolve(context: dict) -> None:
    before = copy.deepcopy(context["current"])
    try:
        context["result"] = resolve_against_current(
            context["current"], context["incoming"]
        )
    except ValueError as exc:
        context["error"] = str(exc)
        context["result"] = None
    context["current_before"] = before


@when("the current business state is rebuilt from all observations")
def rebuild(context: dict) -> None:
    rebuilt = m.build_silver(_bronze_table(context["observed"]))
    context["result"] = rebuilt.to_pylist()


# --- Then ------------------------------------------------------------------


@then(parsers.parse("exactly {count:d} order becomes current"))
@then(parsers.parse("exactly {count:d} orders become current"))
@then(parsers.parse("exactly {count:d} order is current"))
@then(parsers.parse("exactly {count:d} orders are current"))
def exact_current_count(context: dict, count: int) -> None:
    assert len(context["result"]) == count


@then("no order becomes current")
def no_current_change(context: dict) -> None:
    assert context["error"] is None
    assert context["result"] == []


@then(parsers.parse('no change is available to apply for order "{order}"'))
def no_partial_change(context: dict, order: str) -> None:
    # The rejection must abort the whole batch: the caller never receives a
    # change list, so the individually valid order cannot reach Silver either.
    assert (
        context["result"] is None
    ), f"a change list was returned despite the conflict: {context['result']}"


@then(
    parsers.parse(
        'order "{order}" is current at business version {version:d} '
        "with amount {amount:d}"
    )
)
def current_order_is(context: dict, order: str, version: int, amount: int) -> None:
    matching = [row for row in context["result"] if row["order_id"] == order]
    assert len(matching) == 1, f"expected exactly one current row for {order}"
    assert int(matching[0]["business_version"]) == version
    assert float(matching[0]["amount"]) == float(amount)


@then("the previously current state is unchanged")
def current_state_unchanged(context: dict) -> None:
    assert context["current"] == context["current_before"]


@then("the batch is rejected as a business version conflict")
def batch_rejected(context: dict) -> None:
    assert context["error"] is not None, "expected the batch to be rejected"
    assert "FF-14" in context["error"]
