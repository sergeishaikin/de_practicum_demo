"""pytest-bdd steps for shadow validation and the metrics source cutover.

Scope boundary, checked against DoD rule 10 before writing:

* the rollout matrix and the fail-closed cutover behavior are specified here,
  because both are system rules an operator can violate — not properties of a
  Python function;
* the *taxonomy* of a disagreement (missing key, duplicate key, version vs
  payload mismatch) is **not** specified here. Those are comparator internals
  and stay in ``tests/test_m4_gold.py``; the scenario only states that a
  disagreement stops the cycle;
* the live cutover-then-rollback run against a real catalog is specified
  separately in ``gold_cutover.feature`` (T2).

T1 — pure domain, no stack, runs in the default fast suite. Steps bind to the
production callables: ``validate_runtime_config`` for the state machine and
``run`` for the cycle behavior.
"""

from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from common.cutover import validate_runtime_config
from medallion import iceberg_medallion as m
from tests.support.fakes import FakeCatalog, FakeMetrics, FakeTable

scenarios("shadow_cutover.feature")

pytestmark = [pytest.mark.bdd]

TS = datetime(2026, 1, 1, 12, 0, 0)
EVENT_DATE = date(2026, 1, 1)

BRONZE_ID = "bronze.orders"
SILVER_ID = "silver.orders_clean"
GOLD_ID = "gold.orders_daily_metrics"

# The four legal rollout states, in the order an operator walks them. Env var
# names live here rather than in the scenario text — the contract is the stage,
# not the spelling of the switch.
STAGES = {
    "legacy": {"SILVER_MODE": "legacy", "GOLD_SOURCE": "legacy", "SHADOW_COMPARE": "0"},
    "rollback": {"SILVER_MODE": "b2", "GOLD_SOURCE": "legacy", "SHADOW_COMPARE": "0"},
    "shadow": {"SILVER_MODE": "b2", "GOLD_SOURCE": "legacy", "SHADOW_COMPARE": "1"},
    "cutover": {
        "SILVER_MODE": "b2",
        "GOLD_SOURCE": "persisted_silver",
        "SHADOW_COMPARE": "1",
    },
}


def _row(order_id: str, version: int, *, amount: float = 10.0, offset: int = 1) -> dict:
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
        "event_date": EVENT_DATE,
        "business_version": version,
    }


def _table(rows: list[dict]) -> pa.Table:
    return m._rows_to_silver(rows)


# Bronze carries one observation; the incremental state either matches it or
# carries a different business version, which is the minimal disagreement.
OBSERVED = [_row("a", 1)]
AGREEING = [_row("a", 1)]
DISAGREEING = [_row("a", 5, amount=50.0)]


@pytest.fixture
def context(monkeypatch: pytest.MonkeyPatch) -> dict:
    ctx: dict = {"monkeypatch": monkeypatch}
    # The incremental writer has its own specification; here it is a no-op so
    # the scenarios speak only about which projection feeds the metrics.
    monkeypatch.setattr(m, "run_b2", lambda *args, **kwargs: None)
    return ctx


def _stage(context: dict, stage: str) -> None:
    monkeypatch = context["monkeypatch"]
    monkeypatch.setattr(m, "GOLD_SOURCE", STAGES[stage]["GOLD_SOURCE"])
    monkeypatch.setattr(
        m, "SHADOW_COMPARE_ENABLED", STAGES[stage]["SHADOW_COMPARE"] == "1"
    )


def _run_cycle(context: dict, stage: str) -> None:
    _stage(context, stage)
    try:
        m.run(context["catalog"], context["metrics"], "b2")
        context["error"] = None
    except Exception as error:  # noqa: BLE001 - the failure mode is the contract
        context["error"] = error


def _gold(context: dict) -> FakeTable | None:
    return context["catalog"].tables.get(GOLD_ID)


# --- Given -----------------------------------------------------------------


@given(parsers.parse("a runtime configured for the {stage} stage"))
def runtime_stage(context: dict, stage: str) -> None:
    assert stage in STAGES, f"unknown rollout stage {stage!r}"
    context["config"] = STAGES[stage]


@given(
    "a runtime that serves metrics from the incremental state with shadow "
    "validation disabled"
)
def unsafe_runtime(context: dict) -> None:
    context["config"] = {
        "SILVER_MODE": "b2",
        "GOLD_SOURCE": "persisted_silver",
        "SHADOW_COMPARE": "0",
    }


@given(parsers.parse("an incremental business state that {relation} a full rebuild"))
def incremental_state(context: dict, relation: str) -> None:
    persisted = {"agrees with": AGREEING, "disagrees with": DISAGREEING}[relation]
    bronze = FakeTable(_table(OBSERVED))
    silver = FakeTable(_table(persisted))
    context["bronze"] = bronze
    context["silver"] = silver
    context["catalog"] = FakeCatalog({BRONZE_ID: bronze, SILVER_ID: silver})
    context["metrics"] = FakeMetrics()


@given("later observations arrive while the incremental run is in progress")
def late_arrival(context: dict) -> None:
    def ingest_during_run(*args, **kwargs) -> None:
        context["bronze"].df = _table([_row("a", 2, amount=20.0)])

    context["monkeypatch"].setattr(m, "run_b2", ingest_during_run)


@given("a completed cycle with metrics served from the incremental state")
def completed_cutover_cycle(context: dict) -> None:
    _run_cycle(context, "cutover")
    assert context["error"] is None, context["error"]


# --- When ------------------------------------------------------------------


@when("the rollout configuration is validated")
def validate(context: dict) -> None:
    try:
        context["validated"] = validate_runtime_config(context["config"])
        context["error"] = None
    except ValueError as error:
        context["validated"] = None
        context["error"] = error


@when("the cycle runs under shadow validation")
def run_under_shadow(context: dict) -> None:
    _run_cycle(context, "shadow")


@when("the cycle runs with metrics served from the incremental state")
def run_at_cutover(context: dict) -> None:
    _run_cycle(context, "cutover")


@when("the metrics source is rolled back to the full rebuild")
def run_after_rollback(context: dict) -> None:
    # M4 defines rollback as changing the Gold source only, so from `cutover` it
    # lands back in `shadow` — not in the stage the matrix happens to name
    # `rollback`, which also switches validation off.
    _run_cycle(context, "shadow")


# --- Then ------------------------------------------------------------------


@then(parsers.parse("the runtime is accepted as the {stage} stage"))
def runtime_accepted(context: dict, stage: str) -> None:
    assert context["error"] is None, f"stage {stage!r} was refused: {context['error']}"
    assert context["validated"]["rollout"] == stage


@then("the runtime is refused as unsafe")
def runtime_refused(context: dict) -> None:
    assert isinstance(
        context["error"], ValueError
    ), "an unvalidated metrics source was accepted"
    assert context["validated"] is None


@then("the daily metrics are published")
def metrics_published(context: dict) -> None:
    assert context["error"] is None, context["error"]
    gold = _gold(context)
    assert gold is not None, "the daily metrics table was never created"
    assert gold.overwrite_calls == 1
    assert gold.num_rows > 0


@then("the daily metrics still reflect the current business state")
def metrics_reflect_current_state(context: dict) -> None:
    """State, not a write.

    What a rollback owes an operator is that the published metrics describe the
    current business state — not that the cycle performed an overwrite. Counting
    writes made the specification depend on how the metrics got there, which is
    an implementation choice: since GLD-01 a cycle may legitimately decide the
    published state is already the one it would have written and elide the
    rebuild.
    """

    assert context["error"] is None, context["error"]
    gold = _gold(context)
    assert gold is not None, "the daily metrics table was never created"
    assert gold.num_rows > 0
    assert gold.df.to_pylist() == m.build_gold(_table(AGREEING)).to_pylist()


@then("no daily metrics are published")
def metrics_not_published(context: dict) -> None:
    gold = _gold(context)
    # Fail-closed: the abort must precede the write, so either the table was
    # never created or it was never written to.
    assert gold is None or gold.overwrite_calls == 0


@then("the cycle fails closed")
def cycle_failed(context: dict) -> None:
    assert isinstance(context["error"], ValueError), "a disagreement did not stop"


@then("the incremental business state is not rewritten")
def silver_untouched(context: dict) -> None:
    assert context["silver"].overwrite_calls == 0


@then(parsers.parse("the run is recorded as {outcome}"))
def run_recorded(context: dict, outcome: str) -> None:
    expected = {"successful": "success", "a shadow failure": "shadow_failed"}[outcome]
    assert context["metrics"].records, "no operational evidence was recorded"
    cycle = context["metrics"].cycles()[-1]
    assert cycle["source"] == "medallion"
    assert cycle["status"] == expected


@then(parsers.parse("exactly {count:d} shadow comparison is recorded"))
def comparisons_recorded(context: dict, count: int) -> None:
    assert context["metrics"].cycles()[-1]["shadow_comparisons"] == count


@then("shadow validation is still in force")
def shadow_still_on(context: dict) -> None:
    assert (
        context["metrics"].cycles()[-1]["shadow_comparisons"] == 1
    ), "rollback left the deployment without shadow validation"


@then("the disagreement is counted in the recorded evidence")
def mismatch_recorded(context: dict) -> None:
    record = context["metrics"].cycles()[-1]
    assert record["shadow_comparisons"] == 1
    assert record["shadow_mismatches"] >= 1
