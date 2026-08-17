from __future__ import annotations

import json
import sys
from datetime import datetime

import pyarrow as pa
import pytest
from pyiceberg.exceptions import NoSuchTableError

from medallion import legacy_business_version_migration as mig
from medallion.iceberg_medallion import _rows_to_silver
from medallion.legacy_business_version_migration import (
    MIGRATION_MARKER,
    MigrationBlocked,
    backfill_singleton_versions,
    b2_projection,
    migrate,
    profile_legacy_rows,
)
from tests.support.fakes import FakeCatalog, FakeTable

BRONZE_ID = "bronze.orders"
SILVER_ID = "silver.orders_clean"


def rows_table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows)


def silver_image(rows: list[dict]) -> pa.Table:
    """Build a Silver image directly, without going through the collapse rule.

    Constructing the fixture with ``_rows_to_silver`` rather than
    ``b2_projection`` keeps the "did Silver need rewriting?" assertions honest:
    the expected image is not produced by the same function under test.
    """

    return _rows_to_silver(rows)


def lake(
    bronze_rows: list[dict],
    silver_rows: list[dict] | None = None,
    *,
    snapshot_history: int = 1,
) -> tuple[FakeCatalog, FakeTable, FakeTable]:
    bronze = FakeTable(rows_table(bronze_rows), snapshot_history=snapshot_history)
    silver = FakeTable(
        silver_image(silver_rows or []), snapshot_history=snapshot_history
    )
    return FakeCatalog({BRONZE_ID: bronze, SILVER_ID: silver}), bronze, silver


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


def test_profile_handles_bronze_written_before_the_version_column() -> None:
    legacy = {name: value for name, value in row("a", None).items()}
    legacy.pop("business_version")

    profile = profile_legacy_rows(rows_table([legacy]))

    assert profile.migratable
    assert profile.null_rows == 1
    assert profile.versioned_rows == 0


def test_dry_run_reports_the_plan_without_touching_bronze_or_silver() -> None:
    catalog, bronze, silver = lake([row("a", None)])

    result = migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=False)

    assert result["apply"] is False
    assert result["bronze_changed"] is True
    assert result["silver_changed"] is True
    assert result["silver_expected_rows"] == 1
    assert bronze.overwrite_calls == 0
    assert silver.overwrite_calls == 0
    # A dry run must not even claim an "after" identity, or an operator could
    # read the receipt as proof the migration already ran.
    assert "bronze_snapshot_after" not in result
    assert "silver_snapshot_after" not in result
    assert bronze.df["business_version"].to_pylist() == [None]


def test_apply_backfills_bronze_and_silver_with_migration_provenance() -> None:
    catalog, bronze, silver = lake([row("a", None)])

    result = migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=True)

    assert bronze.df["business_version"].to_pylist() == [1]
    assert bronze.snapshot_properties == [
        {
            "business-version-migration": MIGRATION_MARKER,
            "legacy-rule": "singleton-observation-v1",
        }
    ]
    assert silver.snapshot_properties == [
        {
            "business-version-migration": MIGRATION_MARKER,
            "projection": "b2-collapse-delta",
        }
    ]
    assert silver.df.to_pylist()[0]["business_version"] == 1
    assert result["bronze_snapshot_before"] == 1
    assert result["bronze_snapshot_after"] == 2
    assert result["silver_snapshot_before"] == 1
    assert result["silver_snapshot_after"] == 2
    assert result["migration"] == MIGRATION_MARKER


def test_apply_rewrites_stale_silver_without_touching_versioned_bronze() -> None:
    catalog, bronze, silver = lake(
        [row("a", 1, amount=10.0), row("a", 2, amount=20.0)],
        [row("a", 1, amount=10.0)],
    )

    result = migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=True)

    assert result["bronze_changed"] is False
    assert result["silver_changed"] is True
    assert bronze.overwrite_calls == 0
    assert silver.overwrite_calls == 1
    assert silver.df.to_pylist() == [
        {**silver_image([row("a", 2, amount=20.0)]).to_pylist()[0]}
    ]


def test_only_bronze_is_written_when_silver_already_matches() -> None:
    catalog, bronze, silver = lake([row("a", None)], [row("a", 1)])

    result = migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=True)

    assert result["bronze_changed"] is True
    assert result["silver_changed"] is False
    assert bronze.overwrite_calls == 1
    assert silver.overwrite_calls == 0
    assert "silver_snapshot_after" not in result


def test_already_migrated_lake_is_a_no_op_under_apply() -> None:
    catalog, bronze, silver = lake([row("a", 1)], [row("a", 1)])

    result = migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=True)

    assert result["bronze_changed"] is False
    assert result["silver_changed"] is False
    assert bronze.overwrite_calls == 0
    assert silver.overwrite_calls == 0
    assert result["bronze_profile"]["null_rows"] == 0


def test_missing_snapshots_are_reported_as_null_ids() -> None:
    catalog, _bronze, _silver = lake([row("a", 1)], snapshot_history=0)

    result = migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=False)

    assert result["bronze_snapshot_before"] is None
    assert result["silver_snapshot_before"] is None


def test_ambiguous_history_aborts_before_any_table_is_written() -> None:
    catalog, bronze, silver = lake([row("a", None), row("a", None, amount=20.0)])

    with pytest.raises(MigrationBlocked):
        migrate(catalog, bronze_id=BRONZE_ID, silver_id=SILVER_ID, apply=True)

    assert bronze.overwrite_calls == 0
    assert silver.overwrite_calls == 0


def test_main_fails_closed_when_a_table_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["migrate", "--apply"])
    monkeypatch.setattr(mig, "get_catalog", lambda: FakeCatalog({}))

    with pytest.raises(SystemExit) as exit_info:
        mig.main()

    assert "Migration requires existing Bronze and Silver tables" in str(
        exit_info.value
    )
    assert isinstance(exit_info.value.__cause__, NoSuchTableError)


def test_main_defaults_to_a_dry_run(monkeypatch, capsys) -> None:
    catalog, bronze, silver = lake([row("a", None)])
    monkeypatch.setattr(sys, "argv", ["migrate"])
    monkeypatch.setattr(mig, "get_catalog", lambda: catalog)

    mig.main()

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["apply"] is False
    assert receipt["bronze_changed"] is True
    assert bronze.overwrite_calls == 0
    assert silver.overwrite_calls == 0


def test_main_propagates_apply_and_table_identifiers(monkeypatch, capsys) -> None:
    bronze = FakeTable(rows_table([row("a", None)]), snapshot_history=1)
    silver = FakeTable(silver_image([]), snapshot_history=1)
    catalog = FakeCatalog({"lake.bronze": bronze, "lake.silver": silver})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migrate",
            "--apply",
            "--bronze-id",
            "lake.bronze",
            "--silver-id",
            "lake.silver",
        ],
    )
    monkeypatch.setattr(mig, "get_catalog", lambda: catalog)

    mig.main()

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["apply"] is True
    assert bronze.overwrite_calls == 1
    assert silver.overwrite_calls == 1
