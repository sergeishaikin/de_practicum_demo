from __future__ import annotations

from datetime import datetime

import pyarrow as pa
import pytest

from medallion.legacy_business_version_migration import (
    MigrationBlocked,
    backfill_singleton_versions,
    b2_projection,
    profile_legacy_rows,
)


def rows_table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows)


def row(order_id: str, version: int | None, amount: float = 10.0) -> dict:
    return {
        "order_id": order_id,
        "customer": "customer",
        "amount": amount,
        "country": "DE",
        "status": "paid",
        "event_time": datetime(2026, 1, 1, 12),
        "event_date": datetime(2026, 1, 1).date(),
        "kafka_partition": 0,
        "kafka_offset": 10,
        "business_version": version,
    }


def test_legacy_singletons_are_classified_and_backfilled_to_one() -> None:
    source = rows_table([row("a", None), row("b", None)])

    profile = profile_legacy_rows(source)
    migrated, same_profile = backfill_singleton_versions(source)

    assert profile == same_profile
    assert profile.migratable
    assert migrated["business_version"].to_pylist() == [1, 1]
    assert source["business_version"].to_pylist() == [None, None]


def test_backfill_is_idempotent_after_the_first_application() -> None:
    migrated, _ = backfill_singleton_versions(rows_table([row("a", None)]))

    second, profile = backfill_singleton_versions(migrated)

    assert profile.null_rows == 0
    assert second.equals(migrated)


def test_duplicate_or_overlapping_history_fails_closed() -> None:
    duplicate = rows_table([row("a", None), row("a", None, amount=20.0)])
    overlap = rows_table([row("a", None), row("a", 2)])

    for source in (duplicate, overlap):
        with pytest.raises(MigrationBlocked):
            backfill_singleton_versions(source)


def test_b2_projection_collapses_versioned_observations_without_transport_ordering() -> (
    None
):
    source = rows_table([row("a", 1, amount=10.0), row("a", 2, amount=20.0)])

    projected = b2_projection(source)

    assert projected.to_pylist()[0]["business_version"] == 2
    assert projected.to_pylist()[0]["amount"] == 20.0
