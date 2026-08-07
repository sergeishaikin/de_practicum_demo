from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.exceptions import NoSuchTableError
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from common.ops import Metrics

CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://iceberg-rest:8181")
WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")

BRONZE_NAMESPACE = os.getenv("BRONZE_NAMESPACE", "bronze")
BRONZE_TABLE = os.getenv("BRONZE_TABLE", "orders")
SILVER_NAMESPACE = os.getenv("SILVER_NAMESPACE", "silver")
SILVER_TABLE = os.getenv("SILVER_TABLE", "orders_clean")
GOLD_NAMESPACE = os.getenv("GOLD_NAMESPACE", "gold")
GOLD_TABLE = os.getenv("GOLD_TABLE", "orders_daily_metrics")

INTERVAL = int(os.getenv("MEDALLION_INTERVAL_SECONDS", "60"))

VALID_STATUSES = [
    s.strip()
    for s in os.getenv(
        "QUALITY_VALID_STATUSES", "created,paid,shipped,delivered"
    ).split(",")
    if s.strip()
]
FAIL_ON_VIOLATIONS = os.getenv("QUALITY_FAIL_ON_VIOLATIONS", "0") == "1"

SILVER_SCHEMA = Schema(
    NestedField(1, "order_id", StringType(), required=False),
    NestedField(2, "customer", StringType(), required=False),
    NestedField(3, "amount", DoubleType(), required=False),
    NestedField(4, "country", StringType(), required=False),
    NestedField(5, "status", StringType(), required=False),
    NestedField(6, "event_time", TimestampType(), required=False),
    NestedField(7, "kafka_timestamp", TimestampType(), required=False),
    NestedField(8, "kafka_partition", IntegerType(), required=False),
    NestedField(9, "kafka_offset", LongType(), required=False),
    NestedField(10, "event_date", DateType(), required=False),
)

SILVER_PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=10,
        field_id=1000,
        transform=DayTransform(),
        name="event_date_day",
    )
)

GOLD_SCHEMA = Schema(
    NestedField(1, "event_date", DateType(), required=False),
    NestedField(2, "country", StringType(), required=False),
    NestedField(3, "status", StringType(), required=False),
    NestedField(4, "orders_count", LongType(), required=False),
    NestedField(5, "total_amount", DoubleType(), required=False),
    NestedField(6, "avg_amount", DoubleType(), required=False),
    NestedField(7, "distinct_customers", LongType(), required=False),
)


def get_catalog() -> RestCatalog:
    return RestCatalog(
        "default",
        **{
            "uri": CATALOG_URI,
            "warehouse": WAREHOUSE,
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": S3_REGION,
            "s3.path-style-access": "true",
        },
    )


def ensure_table(
    catalog: RestCatalog,
    identifier: str,
    schema: Schema,
    partition_spec: PartitionSpec,
) -> None:
    namespace = identifier.split(".")[0]
    catalog.create_namespace_if_not_exists(namespace)
    try:
        catalog.load_table(identifier)
    except NoSuchTableError:
        catalog.create_table(
            identifier=identifier,
            schema=schema,
            partition_spec=partition_spec,
        )


_SILVER_TYPES: dict[str, pa.DataType] = {
    "order_id": pa.string(),
    "customer": pa.string(),
    "amount": pa.float64(),
    "country": pa.string(),
    "status": pa.string(),
    "event_time": pa.timestamp("us"),
    "kafka_timestamp": pa.timestamp("us"),
    "kafka_partition": pa.int32(),
    "kafka_offset": pa.int64(),
    "event_date": pa.date32(),
}


def _normalize_null_typed_columns(df: pa.Table) -> pa.Table:
    target_fields = [
        (
            pa.field(name, _SILVER_TYPES[name])
            if pa.types.is_null(df.schema.field(name).type) and name in _SILVER_TYPES
            else df.schema.field(name)
        )
        for name in df.column_names
    ]
    if all(t.type.equals(df.schema.field(t.name).type) for t in target_fields):
        return df
    return df.cast(pa.schema(target_fields))


def build_silver(df: pa.Table) -> pa.Table:
    df = _normalize_null_typed_columns(df)
    ordered = df.sort_by([("kafka_offset", "descending")])
    aggs = [
        (name, "hash_first")
        for name in [
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "kafka_timestamp",
            "event_date",
            "kafka_partition",
            "kafka_offset",
        ]
    ]
    deduped = ordered.group_by("order_id", use_threads=False).aggregate(aggs)
    deduped = deduped.rename_columns(
        [
            "order_id",
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "kafka_timestamp",
            "event_date",
            "kafka_partition",
            "kafka_offset",
        ]
    )
    return deduped.select(
        [
            "order_id",
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "kafka_timestamp",
            "kafka_partition",
            "kafka_offset",
            "event_date",
        ]
    )


def build_gold(df: pa.Table) -> pa.Table:
    grouped = df.group_by(["event_date", "country", "status"]).aggregate(
        [
            ("order_id", "count"),
            ("amount", "sum"),
            ("amount", "mean"),
            ("customer", "count_distinct"),
        ]
    )
    return grouped.rename_columns(
        [
            "event_date",
            "country",
            "status",
            "orders_count",
            "total_amount",
            "avg_amount",
            "distinct_customers",
        ]
    )


def run_quality_checks(df: pa.Table) -> dict[str, int]:
    checks: dict[str, int] = {}

    def count(mask: pa.ChunkedArray) -> int:
        value = pc.sum(mask.cast(pa.int64()))
        return int(value.as_py()) if value is not None else 0

    if "order_id" in df.column_names:
        checks["order_id_null"] = count(pc.is_null(df["order_id"]))
    if "amount" in df.column_names:
        checks["amount_null_or_nonpositive"] = count(
            pc.or_(pc.is_null(df["amount"]), pc.less_equal(df["amount"], 0))
        )
    if "country" in df.column_names:
        checks["country_null"] = count(pc.is_null(df["country"]))
    if "status" in df.column_names:
        valid = pc.is_in(df["status"], value_set=pa.array(VALID_STATUSES)).fill_null(
            False
        )
        checks["status_invalid"] = count(pc.invert(valid))
    if "event_time" in df.column_names:
        checks["event_time_null"] = count(pc.is_null(df["event_time"]))

    return {name: value for name, value in checks.items() if value}


def run(catalog: RestCatalog, metrics: Metrics) -> None:
    bronze_id = f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}"
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    gold_id = f"{GOLD_NAMESPACE}.{GOLD_TABLE}"

    started = time.monotonic()
    violations_total = 0

    try:
        bronze = catalog.load_table(bronze_id)
    except NoSuchTableError:
        print("Bronze table not available yet; skipping cycle", flush=True)
        return

    bronze_df = bronze.scan().to_arrow()

    violations = run_quality_checks(bronze_df)
    if violations:
        details = ", ".join(f"{name}={value}" for name, value in violations.items())
        print(f"Quality violations on bronze batch: {details}", flush=True)
        violations_total = sum(violations.values())
        if FAIL_ON_VIOLATIONS:
            print(
                "QUALITY_FAIL_ON_VIOLATIONS is set -> aborting cycle",
                file=sys.stderr,
                flush=True,
            )
            metrics.record(
                source="medallion",
                status="failed",
                bronze_rows=bronze_df.num_rows,
                quality_violations=violations_total,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return

    silver_df = build_silver(bronze_df)
    ensure_table(catalog, silver_id, SILVER_SCHEMA, SILVER_PARTITION_SPEC)
    silver = catalog.load_table(silver_id)
    silver.overwrite(silver_df)
    duplicates_removed = bronze_df.num_rows - silver_df.num_rows
    print(
        f"Silver {silver_id}: overwritten with {silver_df.num_rows} "
        f"deduplicated orders ({duplicates_removed} duplicates removed)",
        flush=True,
    )

    gold_df = build_gold(silver_df)
    ensure_table(catalog, gold_id, GOLD_SCHEMA, PartitionSpec())
    gold = catalog.load_table(gold_id)
    gold.overwrite(gold_df)
    print(
        f"Gold {gold_id}: overwritten with {gold_df.num_rows} daily metrics",
        flush=True,
    )

    metrics.record(
        source="medallion",
        status="success",
        bronze_rows=bronze_df.num_rows,
        silver_rows=silver_df.num_rows,
        gold_rows=gold_df.num_rows,
        duplicates_removed=duplicates_removed,
        quality_violations=violations_total,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def main() -> None:
    print("Iceberg medallion service started (silver + gold)", flush=True)
    catalog = get_catalog()
    metrics = Metrics()
    while True:
        try:
            run(catalog, metrics)
        except Exception as exc:
            print(f"Medallion error: {exc}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()  # pragma: no cover
