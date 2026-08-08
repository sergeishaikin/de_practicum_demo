from __future__ import annotations

from datetime import date

import pytest

from b2_spike import collapse_delta, resolve_against_current


def row(order_id: str, version: int, amount: float, status: str = "paid") -> dict:
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}",
        "amount": amount,
        "status": status,
        "event_time": None,
        "event_date": date(2026, 8, 8),
        "business_version": version,
    }


def test_pre_collapse_picks_highest_version_deterministically() -> None:
    result = collapse_delta([row("x", 3, 30), row("x", 5, 50), row("y", 2, 20)])

    assert [(item["order_id"], item["business_version"]) for item in result] == [
        ("x", 5),
        ("y", 2),
    ]


def test_equal_version_identical_payload_is_idempotent() -> None:
    first = row("x", 5, 50)
    assert collapse_delta([first, dict(first)]) == [first]
    assert resolve_against_current([first], [dict(first)]) == []


def test_equal_version_conflicting_payload_is_ff14() -> None:
    with pytest.raises(ValueError, match="FF-14"):
        collapse_delta([row("x", 5, 50), row("x", 5, 51)])

    with pytest.raises(ValueError, match="FF-14"):
        resolve_against_current([row("x", 5, 50)], [row("x", 5, 51)])


def test_lower_version_does_not_replace_current() -> None:
    assert resolve_against_current([row("x", 5, 50)], [row("x", 3, 30)]) == []


def test_higher_version_replaces_current_and_cross_date_is_allowed() -> None:
    updated = row("x", 2, 20)
    updated["event_date"] = date(2026, 8, 9)

    assert resolve_against_current([row("x", 1, 10)], [updated]) == [updated]
