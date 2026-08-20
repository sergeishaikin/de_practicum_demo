from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from b2_spike import collapse_delta, resolve_against_current
from common.cutover import (
    RUNTIME_ROLLOUT_MATRIX,
    evaluate_cutover_gate,
    validate_runtime_config,
)
from medallion import iceberg_medallion as m

TS = datetime(2026, 8, 8, 12, 0, 0)


def row(
    order_id: str,
    version: int,
    *,
    amount: float,
    event_day: date = date(2026, 8, 8),
    kafka_offset: int = 0,
) -> dict:
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}-v{version}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": TS,
        "kafka_timestamp": TS,
        "kafka_partition": 0,
        "kafka_offset": kafka_offset,
        "event_date": event_day,
        "business_version": version,
    }


@pytest.mark.architecture
def test_ff04_business_version_not_transport_offset() -> None:
    current = [row("order-1", 5, amount=50, kafka_offset=1)]
    late = row("order-1", 3, amount=30, kafka_offset=999)
    assert resolve_against_current(current, [late]) == []

    higher = row("order-1", 6, amount=60, kafka_offset=0)
    assert resolve_against_current(current, [higher]) == [higher]


@pytest.mark.architecture
def test_ff09_cross_date_update_keeps_one_global_current_row() -> None:
    state = [
        row("order-1", 1, amount=10, event_day=date(2026, 8, 8)),
        row("order-2", 1, amount=20),
    ]
    update = row("order-1", 5, amount=50, event_day=date(2026, 8, 9))
    resolved = resolve_against_current(state, [update])
    state = [item for item in state if item["order_id"] != "order-1"] + resolved
    assert len(state) == len({item["order_id"] for item in state}) == 2
    assert (
        next(item for item in state if item["order_id"] == "order-1")[
            "business_version"
        ]
        == 5
    )


@pytest.mark.architecture
def test_ff04_same_batch_collapse_and_replay_are_deterministic() -> None:
    batch = [
        row("order-1", 3, amount=30, kafka_offset=100),
        row("order-1", 5, amount=50, kafka_offset=1),
        row("order-2", 1, amount=20),
    ]
    collapsed = collapse_delta(batch)
    assert [(item["order_id"], item["business_version"]) for item in collapsed] == [
        ("order-1", 5),
        ("order-2", 1),
    ]
    assert resolve_against_current(collapsed, batch) == []


@pytest.mark.architecture
def test_ff14_equal_version_conflict_fails_before_mutation() -> None:
    with pytest.raises(ValueError, match="FF-14"):
        collapse_delta(
            [
                row("order-1", 5, amount=50),
                row("order-1", 5, amount=51),
            ]
        )


@pytest.mark.architecture
def test_legacy_rollback_projection_does_not_use_offset_to_choose_version() -> None:
    silver = m.build_silver(
        m._rows_to_silver(
            [
                row("order-1", 5, amount=50, kafka_offset=1),
                row("order-1", 3, amount=30, kafka_offset=999),
            ]
        )
    )
    assert silver.to_pylist()[0]["business_version"] == 5
    assert silver.to_pylist()[0]["kafka_offset"] == 1


@pytest.mark.architecture
def test_m5_cutover_gate_requires_objective_evidence() -> None:
    config = {
        "SILVER_MODE": "b2",
        "GOLD_SOURCE": "persisted_silver",
        "SHADOW_COMPARE": "1",
    }
    evidence = {
        "shadow_comparison_success": True,
        "unresolved_progress": 0,
        "ff14_conflicts": 0,
        "recent_recovery_tests_passed": True,
        "gold_equivalence": True,
        "rollback_verified": True,
    }
    result = evaluate_cutover_gate(config, evidence)
    assert result["passed"] is True
    assert result["failed_checks"] == []


@pytest.mark.architecture
def test_m5_cutover_gate_fails_closed_on_shadow_or_progress_failure() -> None:
    result = evaluate_cutover_gate(
        {
            "SILVER_MODE": "b2",
            "GOLD_SOURCE": "persisted_silver",
            "SHADOW_COMPARE": "1",
        },
        {
            "shadow_comparison_success": False,
            "unresolved_progress": 1,
            "ff14_conflicts": 0,
            "recent_recovery_tests_passed": True,
            "gold_equivalence": True,
            "rollback_verified": True,
        },
    )
    assert result["passed"] is False
    assert result["failed_checks"] == [
        "shadow_comparison_success",
        "unresolved_progress_zero",
    ]


@pytest.mark.architecture
@pytest.mark.parametrize(
    "config",
    [
        {"SILVER_MODE": "legacy", "GOLD_SOURCE": "legacy", "SHADOW_COMPARE": "0"},
        {"SILVER_MODE": "b2", "GOLD_SOURCE": "legacy", "SHADOW_COMPARE": "1"},
        {
            "SILVER_MODE": "b2",
            "GOLD_SOURCE": "persisted_silver",
            "SHADOW_COMPARE": "1",
        },
    ],
)
def test_runtime_rollout_matrix_accepts_safe_states(config) -> None:
    assert validate_runtime_config(config)["rollout"] in {
        "legacy",
        "shadow",
        "cutover",
    }


@pytest.mark.architecture
def test_runtime_rollout_matrix_holds_exactly_the_four_accepted_states() -> None:
    """Equality, not membership: a fifth key must fail rather than pass unnoticed.

    The two tests around this one assert that specific configurations are
    accepted and that one specific configuration is refused. Both are membership
    claims, so both stay green if some *other* key is added to the matrix - and
    an accepted rollout state arriving as an unnoticed dictionary entry is the
    whole risk POL-01 names. The rollout names are asserted with the keys because
    `validate_runtime_config` returns the name to its caller, so re-pointing
    `("b2", "legacy", "1")` at `cutover` would invert the matrix's meaning while
    leaving its key set untouched.

    See docs/adr/0002-steady-state-shadow-policy.md for why the set is these four
    and what would have to be true before it could become five.
    """

    assert RUNTIME_ROLLOUT_MATRIX == {
        ("legacy", "legacy", "0"): "legacy",
        ("b2", "legacy", "0"): "rollback",
        ("b2", "legacy", "1"): "shadow",
        ("b2", "persisted_silver", "1"): "cutover",
    }


@pytest.mark.architecture
def test_runtime_rollout_rejects_persisted_silver_without_shadow() -> None:
    with pytest.raises(ValueError, match="Unsafe medallion rollout configuration"):
        validate_runtime_config(
            {
                "SILVER_MODE": "b2",
                "GOLD_SOURCE": "persisted_silver",
                "SHADOW_COMPARE": "0",
            }
        )


@pytest.mark.architecture
def test_postgres_serving_upsert_is_monotonic_on_business_version() -> None:
    source = Path("spark/jobs/orders_streaming.py").read_text(encoding="utf-8")
    assert "POSTGRES_VERSION_GUARD" in source
    assert (
        "excluded.business_version > marts.streaming_orders.business_version" in source
    )
