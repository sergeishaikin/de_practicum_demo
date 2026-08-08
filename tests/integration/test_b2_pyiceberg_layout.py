"""SPIKE-2: compare PyIceberg B2 physical layouts.

Run explicitly with a live stack, for example:

    pytest -m spike2 tests/integration/test_b2_pyiceberg_layout.py -s

The test prints one JSON record per layout.  It intentionally does not choose
between the layouts; the result belongs in ADR-0001 after the live run.
"""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import pyarrow as pa
import pytest
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.expressions import In
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import BucketTransform, DayTransform
from pyiceberg.types import (
    DateType,
    DoubleType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from b2_spike import resolve_against_current


ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:18181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:19000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minio")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")

DAYS = int(os.getenv("B2_SPIKE_DAYS", "10"))
ORDERS_PER_DAY = int(os.getenv("B2_SPIKE_ORDERS_PER_DAY", "1000"))
CHUNKS_PER_DAY = int(os.getenv("B2_SPIKE_CHUNKS_PER_DAY", "4"))
BUCKET_COUNT = int(os.getenv("B2_SPIKE_BUCKET_COUNT", "16"))

SILVER_SCHEMA = Schema(
    NestedField(1, "order_id", StringType(), required=False),
    NestedField(2, "customer", StringType(), required=False),
    NestedField(3, "amount", DoubleType(), required=False),
    NestedField(4, "status", StringType(), required=False),
    NestedField(5, "event_time", TimestampType(), required=False),
    NestedField(6, "event_date", DateType(), required=False),
    NestedField(7, "business_version", LongType(), required=False),
)

DAY_PARTITION = PartitionSpec(
    PartitionField(
        source_id=6,
        field_id=1000,
        transform=DayTransform(),
        name="event_date_day",
    )
)

BUCKET_PARTITION = PartitionSpec(
    PartitionField(
        source_id=1,
        field_id=1000,
        transform=BucketTransform(BUCKET_COUNT),
        name=f"order_id_bucket_{BUCKET_COUNT}",
    )
)


def catalog() -> RestCatalog:
    return RestCatalog(
        "default",
        **{
            "uri": ICEBERG_CATALOG_URI,
            "warehouse": ICEBERG_WAREHOUSE,
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": "us-east-1",
            "s3.path-style-access": "true",
        },
    )


@pytest.fixture
def spike_namespace():
    namespace = f"spike2_{uuid.uuid4().hex[:8]}"
    cat = catalog()
    cat.create_namespace_if_not_exists(namespace)
    yield namespace
    for table_name in ("b2a_day", "b2b_bucket"):
        try:
            cat.drop_table(f"{namespace}.{table_name}")
        except Exception:
            pass
    try:
        cat.drop_namespace(namespace)
    except Exception:
        pass


def make_row(
    order_id: str,
    *,
    day: date,
    version: int,
    amount: float,
    status: str = "paid",
) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "customer": f"customer-{order_id}",
        "amount": amount,
        "status": status,
        "event_time": datetime(day.year, day.month, day.day, 12),
        "event_date": day,
        "business_version": version,
    }


def rows_to_arrow(rows: list[dict[str, Any]]) -> pa.Table:
    return pa.table(
        {
            "order_id": pa.array([row["order_id"] for row in rows], type=pa.string()),
            "customer": pa.array([row["customer"] for row in rows], type=pa.string()),
            "amount": pa.array([row["amount"] for row in rows], type=pa.float64()),
            "status": pa.array([row["status"] for row in rows], type=pa.string()),
            "event_time": pa.array(
                [row["event_time"] for row in rows], type=pa.timestamp("us")
            ),
            "event_date": pa.array(
                [row["event_date"] for row in rows], type=pa.date32()
            ),
            "business_version": pa.array(
                [row["business_version"] for row in rows], type=pa.int64()
            ),
        }
    )


def seed_rows(day_index: int, start: int, stop: int) -> list[dict[str, Any]]:
    day = date(2026, 8, 1) + timedelta(days=day_index)
    return [
        make_row(
            f"order-{day_index:02d}-{row_index:05d}",
            day=day,
            version=1,
            amount=float(row_index + 1),
        )
        for row_index in range(start, stop)
    ]


def seed_table(table) -> int:
    if ORDERS_PER_DAY % CHUNKS_PER_DAY:
        raise ValueError("B2_SPIKE_ORDERS_PER_DAY must divide evenly by chunks per day")
    chunk_size = ORDERS_PER_DAY // CHUNKS_PER_DAY
    total = 0
    for day_index in range(DAYS):
        for chunk in range(CHUNKS_PER_DAY):
            rows = seed_rows(
                day_index,
                chunk * chunk_size,
                (chunk + 1) * chunk_size,
            )
            table.append(rows_to_arrow(rows))
            total += len(rows)
    return total


def update_batch() -> list[dict[str, Any]]:
    """Ten affected keys, including cross-date and same-batch version cases."""

    later = date(2026, 8, DAYS + 5)
    rows = [
        make_row(
            "order-00-00000", day=later, version=3, amount=300, status="shipped"
        ),
        make_row(
            "order-00-00000", day=later, version=5, amount=500, status="delivered"
        ),
    ]
    for index in range(1, 10):
        rows.append(
            make_row(
                f"order-{index:02d}-{index:05d}",
                day=later,
                version=2,
                amount=200 + index,
                status="shipped",
            )
        )
    return rows


def row_filter(keys: list[str]) -> In:
    return In("order_id", keys)


def live_data_files(table) -> dict[str, int]:
    return {
        item["file_path"]: item["file_size_in_bytes"]
        for item in table.inspect.data_files().to_pylist()
    }


def partition_file_counts(table, partition_field: str) -> Counter:
    """Return live data-file counts by the table's physical partition value."""

    return Counter(
        item["partition"][partition_field]
        for item in table.inspect.data_files().to_pylist()
    )


def planned_read_metrics(table, keys: list[str]) -> dict[str, int]:
    tasks = list(table.scan(row_filter=row_filter(keys)).plan_files())
    return {
        "files_planned_for_read": len(tasks),
        "bytes_planned_for_read": sum(
            task.file.file_size_in_bytes for task in tasks
        ),
    }


def apply_b2_update(table, incoming: list[dict[str, Any]]) -> dict[str, int]:
    collapsed_keys = sorted({row["order_id"] for row in incoming})
    current = table.scan(row_filter=row_filter(collapsed_keys)).to_arrow().to_pylist()
    resolved = resolve_against_current(current, incoming)
    changed_keys = sorted({row["order_id"] for row in resolved})
    before_files = live_data_files(table)
    before_snapshots = len(table.metadata.snapshots)
    metrics = planned_read_metrics(table, changed_keys or collapsed_keys)

    if changed_keys:
        table.overwrite(
            rows_to_arrow(resolved),
            overwrite_filter=row_filter(changed_keys),
            snapshot_properties={"spike": "SPIKE-2", "changed_keys": str(len(changed_keys))},
        )

    after_files = live_data_files(table)
    removed = set(before_files) - set(after_files)
    added = set(after_files) - set(before_files)
    metrics.update(
        {
            "data_files_removed": len(removed),
            "data_files_added": len(added),
            "bytes_removed": sum(before_files[path] for path in removed),
            "bytes_added": sum(after_files[path] for path in added),
            "snapshot_count_delta": len(table.metadata.snapshots) - before_snapshots,
            "changed_keys": len(changed_keys),
        }
    )
    return metrics


def logical_state(table) -> dict[str, tuple[int, float, str, date]]:
    rows = table.scan().to_arrow().to_pylist()
    return {
        row["order_id"]: (
            row["business_version"],
            row["amount"],
            row["status"],
            row["event_date"],
        )
        for row in rows
    }


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.spike2
def test_b2_layouts_preserve_correctness_and_emit_cost_evidence(spike_namespace):
    cat = catalog()
    incoming = update_batch()
    incoming_keys = sorted({row["order_id"] for row in incoming})
    if DAYS < len(incoming_keys):
        raise ValueError("B2_SPIKE_DAYS must be at least 10 for this fixture")
    bucket_transform = BucketTransform(BUCKET_COUNT).transform(StringType())
    assert len({bucket_transform(key) for key in incoming_keys}) >= 2
    results = []

    for table_name, partition_spec, layout, partition_field in (
        ("b2a_day", DAY_PARTITION, "B2a day(event_date)", "event_date_day"),
        (
            "b2b_bucket",
            BUCKET_PARTITION,
            f"B2b bucket(order_id,{BUCKET_COUNT})",
            f"order_id_bucket_{BUCKET_COUNT}",
        ),
    ):
        identifier = f"{spike_namespace}.{table_name}"
        cat.create_table(identifier, schema=SILVER_SCHEMA, partition_spec=partition_spec)
        table = cat.load_table(identifier)
        seeded_rows = seed_table(table)
        initial_files = live_data_files(table)
        initial_data_files = len(initial_files)
        initial_data_bytes = sum(initial_files.values())
        initial_partition_files = partition_file_counts(table, partition_field)
        assert initial_data_files >= DAYS * CHUNKS_PER_DAY
        assert len(initial_partition_files) >= 2
        assert min(initial_partition_files.values()) >= 2

        current_targets = table.scan(row_filter=row_filter(incoming_keys)).to_arrow()
        current_target_rows = current_targets.to_pylist()
        assert len({row["event_date"] for row in current_target_rows}) >= 2
        assert any(
            row["order_id"] == "order-00-00000"
            and row["event_date"] != incoming[0]["event_date"]
            for row in current_target_rows
        )
        first_update = apply_b2_update(table, incoming)
        first_update.update(
            {
                "initial_data_files": initial_data_files,
                "initial_data_bytes": initial_data_bytes,
                "planned_files_fraction": round(
                    first_update["files_planned_for_read"] / initial_data_files, 6
                ),
                "planned_bytes_fraction": round(
                    first_update["bytes_planned_for_read"] / initial_data_bytes, 6
                ),
                "removed_files_fraction": round(
                    first_update["data_files_removed"] / initial_data_files, 6
                ),
                "removed_bytes_fraction": round(
                    first_update["bytes_removed"] / initial_data_bytes, 6
                ),
            }
        )

        state = logical_state(table)
        assert len(state) == seeded_rows
        assert len(state) == len(set(state))
        assert state["order-00-00000"] == (
            5,
            500.0,
            "delivered",
            date(2026, 8, DAYS + 5),
        )
        assert state["order-01-00001"][0] == 2

        replay = apply_b2_update(table, incoming)
        assert replay["changed_keys"] == 0
        assert replay["snapshot_count_delta"] == 0
        assert logical_state(table) == state

        lower_version = [
            make_row(
                "order-00-00000",
                day=date(2026, 8, DAYS + 6),
                version=3,
                amount=300,
                status="shipped",
            )
        ]
        lower = apply_b2_update(table, lower_version)
        assert lower["changed_keys"] == 0
        assert logical_state(table) == state

        results.append(
            {
                "layout": layout,
                "seeded_rows": seeded_rows,
                "initial_data_files": initial_data_files,
                "initial_partition_files": {
                    str(key): value
                    for key, value in initial_partition_files.items()
                },
                "first_update": first_update,
                "replay": replay,
                "lower_version": lower,
            }
        )

    print("SPIKE-2_RESULT " + json.dumps(results, sort_keys=True, default=str))
