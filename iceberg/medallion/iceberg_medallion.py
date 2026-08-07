from __future__ import annotations

import os
import sys
import time

import pyarrow as pa
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


def build_silver(df: pa.Table) -> pa.Table:
    ordered = df.sort_by([("kafka_offset", "descending")])
    aggs = [
        (name, "hash_first")
        for name in [
            "order_id",
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "event_date",
            "kafka_partition",
        ]
    ]
    aggs.append(("kafka_offset", "hash_first"))
    deduped = ordered.group_by("order_id", use_threads=False).aggregate(aggs)
    return deduped.rename_columns(
        [
            "order_id",
            "customer",
            "amount",
            "country",
            "status",
            "event_time",
            "event_date",
            "kafka_partition",
            "kafka_offset",
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


def run(catalog: RestCatalog) -> None:
    bronze_id = f"{BRONZE_NAMESPACE}.{BRONZE_TABLE}"
    silver_id = f"{SILVER_NAMESPACE}.{SILVER_TABLE}"
    gold_id = f"{GOLD_NAMESPACE}.{GOLD_TABLE}"

    try:
        bronze = catalog.load_table(bronze_id)
    except NoSuchTableError:
        print("Bronze table not available yet; skipping cycle", flush=True)
        return

    bronze_df = bronze.scan().to_arrow()

    silver_df = build_silver(bronze_df)
    ensure_table(catalog, silver_id, SILVER_SCHEMA, SILVER_PARTITION_SPEC)
    silver = catalog.load_table(silver_id)
    silver.overwrite(silver_df)
    print(
        f"Silver {silver_id}: overwritten with {silver_df.num_rows} "
        f"deduplicated orders",
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


def main() -> None:
    print("Iceberg medallion service started (silver + gold)", flush=True)
    catalog = get_catalog()
    while True:
        try:
            run(catalog)
        except Exception as exc:
            print(f"Medallion error: {exc}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
