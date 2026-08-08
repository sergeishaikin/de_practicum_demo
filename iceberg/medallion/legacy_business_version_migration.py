"""One-shot, fail-closed migration for pre-M1 Bronze observations.

The only accepted legacy rule is ``singleton legacy observation -> version 1``.
This module deliberately does not derive a domain version from transport
metadata.  It is a bounded migration tool, not part of the steady-state B2
processor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.exceptions import NoSuchTableError

REPO_ICEBERG_DIR = Path(__file__).resolve().parents[1]
if str(REPO_ICEBERG_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_ICEBERG_DIR))

from b2_spike import collapse_delta  # noqa: E402
from medallion.iceberg_medallion import (  # noqa: E402
    SILVER_NAMESPACE,
    SILVER_TABLE,
    _rows_to_silver,
    get_catalog,
)

LEGACY_VERSION = 1
MIGRATION_MARKER = "legacy-singleton-business-version-v1"
PAYLOAD_COLUMNS = (
    "customer",
    "amount",
    "country",
    "status",
    "event_time",
    "event_date",
)


@dataclass(frozen=True)
class LegacyProfile:
    total_rows: int
    null_rows: int
    distinct_null_order_ids: int
    duplicate_order_ids: int
    payload_conflict_order_ids: int
    null_ids_overlapping_versioned_ids: int
    versioned_rows: int
    null_order_ids: int

    @property
    def migratable(self) -> bool:
        return (
            self.duplicate_order_ids == 0
            and self.payload_conflict_order_ids == 0
            and self.null_ids_overlapping_versioned_ids == 0
            and self.null_order_ids == 0
        )


class MigrationBlocked(RuntimeError):
    """Raised when legacy history is not safe to classify automatically."""


def _payload_key(row: dict) -> tuple:
    values = []
    for column in PAYLOAD_COLUMNS:
        value = row.get(column)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        values.append(value)
    return tuple(values)


def _with_version_column(table: pa.Table) -> pa.Table:
    if "business_version" in table.column_names:
        return table
    return table.append_column(
        "business_version", pa.array([None] * table.num_rows, type=pa.int64())
    )


def profile_legacy_rows(table: pa.Table) -> LegacyProfile:
    """Classify NULL-version rows without changing the input table."""

    rows = _with_version_column(table).to_pylist()
    null_rows = [row for row in rows if row.get("business_version") is None]
    null_by_id: dict[str, list[dict]] = {}
    versioned_ids: set[str] = set()
    for row in rows:
        order_id = row.get("order_id")
        if row.get("business_version") is None:
            null_by_id.setdefault(order_id, []).append(row)
        else:
            versioned_ids.add(order_id)

    duplicate_ids = {
        order_id for order_id, items in null_by_id.items() if len(items) > 1
    }
    payload_conflicts = {
        order_id
        for order_id, items in null_by_id.items()
        if len({_payload_key(item) for item in items}) > 1
    }
    null_ids = set(null_by_id)
    return LegacyProfile(
        total_rows=len(rows),
        null_rows=len(null_rows),
        distinct_null_order_ids=len(null_ids),
        duplicate_order_ids=len(duplicate_ids),
        payload_conflict_order_ids=len(payload_conflicts),
        null_ids_overlapping_versioned_ids=len(null_ids & versioned_ids),
        versioned_rows=sum(row.get("business_version") is not None for row in rows),
        null_order_ids=sum(row.get("order_id") is None for row in null_rows),
    )


def assert_migratable(profile: LegacyProfile) -> None:
    if not profile.migratable:
        raise MigrationBlocked(
            "Legacy business_version migration is ambiguous: "
            f"{json.dumps(asdict(profile), sort_keys=True)}"
        )


def backfill_singleton_versions(table: pa.Table) -> tuple[pa.Table, LegacyProfile]:
    """Return a copy with safe legacy NULLs assigned version 1."""

    table = _with_version_column(table)
    profile = profile_legacy_rows(table)
    assert_migratable(profile)
    if profile.null_rows == 0:
        return table, profile

    version_index = table.column_names.index("business_version")
    current = table.column("business_version").to_pylist()
    values = [LEGACY_VERSION if value is None else int(value) for value in current]
    return table.set_column(
        version_index,
        "business_version",
        pa.chunked_array([pa.array(values, type=pa.int64())]),
    ), profile


def _row_key(row: dict) -> tuple:
    values = []
    for name, value in sorted(row.items()):
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        values.append((name, type(value).__name__, repr(value)))
    return tuple(values)


def _same_rows(left: pa.Table, right: pa.Table) -> bool:
    left_rows = sorted(_row_key(row) for row in left.to_pylist())
    right_rows = sorted(_row_key(row) for row in right.to_pylist())
    return left_rows == right_rows


def b2_projection(bronze_table: pa.Table) -> pa.Table:
    """Build the migrated Silver image using the accepted B2 collapse rule."""

    rows = collapse_delta(_with_version_column(bronze_table).to_pylist())
    return _rows_to_silver(rows)


def _snapshot_id(table) -> int | None:
    snapshot = table.current_snapshot()
    return snapshot.snapshot_id if snapshot else None


def migrate(
    catalog: RestCatalog,
    *,
    bronze_id: str,
    silver_id: str,
    apply: bool,
) -> dict:
    """Profile, optionally backfill Bronze, and reconcile Silver once."""

    bronze = catalog.load_table(bronze_id)
    silver = catalog.load_table(silver_id)
    bronze_before = bronze.scan().to_arrow()
    silver_before = silver.scan().to_arrow()
    bronze_after, bronze_profile = backfill_singleton_versions(bronze_before)
    expected_silver = b2_projection(bronze_after)
    result = {
        "migration": MIGRATION_MARKER,
        "apply": apply,
        "bronze_profile": asdict(bronze_profile),
        "bronze_snapshot_before": _snapshot_id(bronze),
        "silver_snapshot_before": _snapshot_id(silver),
        "bronze_changed": not _same_rows(bronze_before, bronze_after),
        "silver_changed": not _same_rows(silver_before, expected_silver),
        "silver_expected_rows": expected_silver.num_rows,
    }
    if not apply:
        return result

    if result["bronze_changed"]:
        bronze.overwrite(
            bronze_after,
            snapshot_properties={
                "business-version-migration": MIGRATION_MARKER,
                "legacy-rule": "singleton-observation-v1",
            },
        )
        result["bronze_snapshot_after"] = _snapshot_id(bronze)
    if result["silver_changed"]:
        silver.overwrite(
            expected_silver,
            snapshot_properties={
                "business-version-migration": MIGRATION_MARKER,
                "projection": "b2-collapse-delta",
            },
        )
        result["silver_snapshot_after"] = _snapshot_id(silver)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the migration")
    parser.add_argument(
        "--bronze-id",
        default=(
            f"{os.getenv('BRONZE_NAMESPACE', 'bronze')}."
            f"{os.getenv('BRONZE_TABLE', 'orders')}"
        ),
    )
    parser.add_argument("--silver-id", default=f"{SILVER_NAMESPACE}.{SILVER_TABLE}")
    args = parser.parse_args()
    try:
        result = migrate(
            get_catalog(),
            bronze_id=args.bronze_id,
            silver_id=args.silver_id,
            apply=args.apply,
        )
    except NoSuchTableError as exc:
        raise SystemExit(
            f"Migration requires existing Bronze and Silver tables: {exc}"
        ) from exc
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
