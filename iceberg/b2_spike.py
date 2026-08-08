"""Pure B2 projection helpers used by the SPIKE-2 test harness.

This module deliberately does not own a catalog or a control table.  It only
captures the deterministic part of the PyIceberg-owned projection so that the
correctness gates can run without a live stack.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


BUSINESS_COLUMNS = (
    "customer",
    "amount",
    "status",
    "event_time",
    "event_date",
)


def _payload_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(column) for column in BUSINESS_COLUMNS)


def collapse_delta(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse one incoming batch to one deterministic row per business key.

    The highest ``business_version`` wins.  Equal versions are allowed only
    when their business payload is identical; conflicting payloads are FF-14
    violations and abort before any table mutation.
    """

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = row.get("order_id")
        if not key:
            raise ValueError("B2 delta contains a null or empty order_id")
        if row.get("business_version") is None:
            raise ValueError(f"B2 delta has no business_version for {key}")
        by_key[key].append(row)

    resolved: list[dict[str, Any]] = []
    for key, candidates in by_key.items():
        by_version: dict[int, set[tuple[Any, ...]]] = defaultdict(set)
        for candidate in candidates:
            by_version[int(candidate["business_version"])].add(
                _payload_signature(candidate)
            )
        conflicting = [version for version, payloads in by_version.items() if len(payloads) > 1]
        if conflicting:
            versions = ", ".join(str(version) for version in sorted(conflicting))
            raise ValueError(
                f"FF-14: conflicting payload for order_id={key!r}, "
                f"business_version={versions}"
            )
        resolved.append(
            max(candidates, key=lambda candidate: int(candidate["business_version"]))
        )

    return sorted(resolved, key=lambda row: str(row["order_id"]))


def resolve_against_current(
    current_rows: list[dict[str, Any]], incoming_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return only rows that must replace or create current Silver rows.

    A lower version and an identical replay are no-ops.  A same-version,
    different-payload collision with persisted Silver is also FF-14 and is
    rejected before the caller invokes ``overwrite``.
    """

    current_by_key = {row["order_id"]: row for row in current_rows}
    resolved = collapse_delta(incoming_rows)
    changed: list[dict[str, Any]] = []

    for incoming in resolved:
        key = incoming["order_id"]
        current = current_by_key.get(key)
        if current is None:
            changed.append(incoming)
            continue

        incoming_version = int(incoming["business_version"])
        current_version = int(current["business_version"])
        if incoming_version == current_version:
            if _payload_signature(incoming) != _payload_signature(current):
                raise ValueError(
                    f"FF-14: persisted payload conflict for order_id={key!r}, "
                    f"business_version={incoming_version}"
                )
            continue
        if incoming_version > current_version:
            changed.append(incoming)

    return sorted(changed, key=lambda row: str(row["order_id"]))
