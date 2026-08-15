from __future__ import annotations

import os
import subprocess
import uuid
from datetime import date, datetime

import pyarrow as pa
import pytest
from pyarrow.fs import S3FileSystem
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.partitioning import PartitionSpec

from medallion import iceberg_medallion as m

ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:18181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:19000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minio")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")

TABLES = ("bronze_orders", "silver_orders_clean", "gold_metrics", "orders")


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


def fs() -> S3FileSystem:
    return S3FileSystem(
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        endpoint_override=S3_ENDPOINT,
        region="us-east-1",
        scheme="http",
    )


def trino_raw(sql: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "de-demo-trino",
            "trino",
            "--catalog",
            "iceberg",
            "--execute",
            sql,
            "--output-format",
            "CSV_HEADER",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"trino failed: {proc.stderr.strip()} | sql: {sql}")
    return proc.stdout


def trino_scalar(sql: str) -> str:
    lines = [line for line in trino_raw(sql).splitlines() if line.strip()]
    assert len(lines) >= 2, f"expected header+row from trino: {sql}"
    return lines[1].strip().strip('"')


def trino_exec(sql: str) -> None:
    trino_raw(sql)


@pytest.fixture
def lake_schema():
    ns = f"test_{uuid.uuid4().hex[:8]}"
    yield ns
    cat = catalog()
    for table in TABLES:
        try:
            cat.drop_table(f"{ns}.{table}")
        except Exception:
            pass
    try:
        cat.drop_namespace(ns)
    except Exception:
        pass
    trino_exec(f"DROP SCHEMA IF EXISTS iceberg.{ns} CASCADE")


def orders_table(rows: list[tuple]) -> pa.Table:
    ts = datetime(2026, 1, 1, 12, 0, 0)
    d = date(2026, 1, 1)
    return pa.table(
        {
            "order_id": pa.array([r[0] for r in rows], type=pa.string()),
            "customer": pa.array([r[1] for r in rows], type=pa.string()),
            "amount": pa.array([r[2] for r in rows], type=pa.float64()),
            "country": pa.array([r[3] for r in rows], type=pa.string()),
            "status": pa.array([r[4] for r in rows], type=pa.string()),
            "event_time": pa.array([ts] * len(rows), type=pa.timestamp("us")),
            "kafka_timestamp": pa.array([ts] * len(rows), type=pa.timestamp("us")),
            "kafka_partition": pa.array([r[5] for r in rows], type=pa.int32()),
            "kafka_offset": pa.array([r[6] for r in rows], type=pa.int64()),
            "event_date": pa.array([d] * len(rows), type=pa.date32()),
            "business_version": pa.array([r[6] for r in rows], type=pa.int64()),
        }
    )


def ensure_table(cat: RestCatalog, identifier: str, is_gold: bool = False) -> None:
    schema = m.GOLD_SCHEMA if is_gold else m.SILVER_SCHEMA
    spec = m.SILVER_PARTITION_SPEC if not is_gold else PartitionSpec()
    m.ensure_table(cat, identifier, schema, spec)


def snapshot_count(cat: RestCatalog, identifier: str) -> int:
    return len(list(cat.load_table(identifier).metadata.snapshots))


def current_load_id(cat: RestCatalog, identifier: str) -> str:
    table = cat.load_table(identifier)
    snaps = list(table.metadata.snapshots)
    assert snaps, f"no snapshots for {identifier}"
    props = snaps[-1].summary.additional_properties
    return props["load-id"]


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_catalog_and_table_creation_visible_in_trino(lake_schema):
    cat = catalog()
    ns = lake_schema
    identifier = f"{ns}.orders"
    ensure_table(cat, identifier)
    assert cat.load_table(identifier) is not None
    assert (ns,) in cat.list_namespaces()
    assert "orders" in trino_raw(f"SHOW TABLES FROM iceberg.{ns}")


@pytest.mark.integration
@pytest.mark.iceberg
def test_append_increases_snapshot_and_records_load_id(lake_schema):
    cat = catalog()
    ns = lake_schema
    identifier = f"{ns}.orders"
    ensure_table(cat, identifier)
    assert snapshot_count(cat, identifier) == 0

    table = cat.load_table(identifier)
    table.append(
        orders_table([("a", "c1", 10.0, "US", "paid", 0, 1)]),
        snapshot_properties={"load-id": "test-load-1"},
    )
    assert snapshot_count(cat, identifier) == 1
    assert current_load_id(cat, identifier) == "test-load-1"

    table.append(
        orders_table([("b", "c2", 20.0, "US", "paid", 0, 2)]),
        snapshot_properties={"load-id": "test-load-2"},
    )
    assert snapshot_count(cat, identifier) == 2
    assert current_load_id(cat, identifier) == "test-load-2"
    assert cat.load_table(identifier).scan().to_arrow().num_rows == 2


@pytest.mark.integration
@pytest.mark.iceberg
def test_silver_dedup_latest_offset_wins(lake_schema):
    cat = catalog()
    ns = lake_schema
    bronze = f"{ns}.bronze_orders"
    silver = f"{ns}.silver_orders_clean"
    ensure_table(cat, bronze)
    cat.load_table(bronze).append(
        orders_table(
            [
                ("a", "cust1", 10.0, "US", "paid", 0, 1),
                ("a", "cust2", 50.0, "US", "paid", 1, 5),
                ("b", "cust3", 30.0, "DE", "created", 2, 3),
            ]
        ),
        snapshot_properties={"load-id": "dedup"},
    )
    bronze_df = cat.load_table(bronze).scan().to_arrow()
    silver_df = m.build_silver(bronze_df)
    assert silver_df.num_rows == 2
    assert m.build_gold(silver_df).num_rows == 2
    silver_arrow = silver_df.to_pydict()
    assert silver_arrow["order_id"] == ["a", "b"]
    assert silver_arrow["amount"] == [50.0, 30.0]
    assert silver_arrow["kafka_offset"] == [5, 3]

    ensure_table(cat, silver)
    cat.load_table(silver).overwrite(silver_df)
    assert cat.load_table(silver).scan().to_arrow().num_rows == 2


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_gold_aggregation_exact_values(lake_schema):
    cat = catalog()
    ns = lake_schema
    bronze = f"{ns}.bronze_orders"
    gold = f"{ns}.gold_metrics"
    ensure_table(cat, bronze)
    cat.load_table(bronze).append(
        orders_table(
            [
                ("uk1", "custA", 250.0, "UK", "paid", 0, 1),
                ("uk2", "custB", 300.0, "UK", "paid", 1, 2),
                ("uk3", "custA", 400.0, "UK", "paid", 2, 3),
                ("uk4", "custB", 300.0, "UK", "paid", 3, 4),
                ("us1", "custC", 100.0, "US", "paid", 4, 5),
                ("us2", "custD", 200.0, "US", "paid", 5, 6),
                ("us3", "custC", 300.0, "US", "paid", 6, 7),
                ("us4", "custD", 300.0, "US", "paid", 7, 8),
            ]
        ),
        snapshot_properties={"load-id": "gold"},
    )
    bronze_df = cat.load_table(bronze).scan().to_arrow()
    silver_df = m.build_silver(bronze_df)
    gold_df = m.build_gold(silver_df)
    rows = gold_df.to_pydict()
    uk = {
        "orders_count": rows["orders_count"][rows["country"].index("UK")],
        "total_amount": rows["total_amount"][rows["country"].index("UK")],
        "distinct_customers": rows["distinct_customers"][rows["country"].index("UK")],
    }
    us = {
        "orders_count": rows["orders_count"][rows["country"].index("US")],
        "total_amount": rows["total_amount"][rows["country"].index("US")],
        "distinct_customers": rows["distinct_customers"][rows["country"].index("US")],
    }
    assert uk == {"orders_count": 4, "total_amount": 1250.0, "distinct_customers": 2}
    assert us == {"orders_count": 4, "total_amount": 900.0, "distinct_customers": 2}
    assert sum(rows["total_amount"]) == 2150.0

    ensure_table(cat, gold, is_gold=True)
    cat.load_table(gold).overwrite(gold_df)
    assert (
        trino_scalar(
            f"SELECT total_amount FROM iceberg.{ns}.gold_metrics WHERE country = 'UK'"
        )
        == "1250.0"
    )
    assert (
        trino_scalar(
            f"SELECT total_amount FROM iceberg.{ns}.gold_metrics WHERE country = 'US'"
        )
        == "900.0"
    )


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_trino_select_across_layers(lake_schema):
    cat = catalog()
    ns = lake_schema
    bronze = f"{ns}.bronze_orders"
    silver = f"{ns}.silver_orders_clean"
    gold = f"{ns}.gold_metrics"
    for ident, is_gold in ((bronze, False), (silver, False), (gold, True)):
        ensure_table(cat, ident, is_gold=is_gold)

    cat.load_table(bronze).append(
        orders_table(
            [
                ("a", "cust1", 10.0, "UK", "paid", 0, 1),
                ("b", "cust2", 20.0, "US", "paid", 1, 2),
                ("c", "cust3", 30.0, "US", "paid", 2, 3),
            ]
        ),
        snapshot_properties={"load-id": "layer"},
    )
    bronze_df = cat.load_table(bronze).scan().to_arrow()
    silver_df = m.build_silver(bronze_df)
    gold_df = m.build_gold(silver_df)
    cat.load_table(silver).overwrite(silver_df)
    cat.load_table(gold).overwrite(gold_df)

    assert trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.bronze_orders") == "3"
    assert trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.silver_orders_clean") == "3"
    assert (
        trino_scalar(f"SELECT sum(total_amount) FROM iceberg.{ns}.gold_metrics")
        == "60.0"
    )
    assert (
        trino_scalar(
            f"SELECT count(*) FROM iceberg.{ns}.bronze_orders WHERE country = 'UK'"
        )
        == "1"
    )


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_time_travel_snapshot_history(lake_schema):
    cat = catalog()
    ns = lake_schema
    identifier = f"{ns}.orders"
    ensure_table(cat, identifier)
    table = cat.load_table(identifier)

    table.append(
        orders_table([("a", "c1", 10.0, "US", "paid", 0, 1)]),
        snapshot_properties={"load-id": "t1"},
    )
    first_id = table.metadata.snapshots[-1].snapshot_id
    table.append(
        orders_table([("b", "c2", 20.0, "US", "paid", 0, 2)]),
        snapshot_properties={"load-id": "t2"},
    )
    assert snapshot_count(cat, identifier) == 2

    assert trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.orders") == "2"
    assert (
        trino_scalar(
            f"SELECT count(*) FROM iceberg.{ns}.orders FOR VERSION AS OF {first_id}"
        )
        == "1"
    )


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_maintenance_procedures(lake_schema):
    cat = catalog()
    ns = lake_schema
    identifier = f"{ns}.orders"
    ensure_table(cat, identifier)
    table = cat.load_table(identifier)
    for i in range(3):
        table.append(
            orders_table([(f"o{i}", "c1", 10.0, "US", "paid", 0, i)]),
            snapshot_properties={"load-id": f"m{i}"},
        )
    before = snapshot_count(cat, identifier)
    assert before == 3

    trino_exec(
        f"ALTER TABLE iceberg.{ns}.orders EXECUTE optimize(file_size_threshold => '5MB')"
    )
    after_optimize = snapshot_count(cat, identifier)
    assert trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.orders") == "3"
    assert after_optimize >= before

    trino_exec(
        f"ALTER TABLE iceberg.{ns}.orders EXECUTE expire_snapshots("
        "retention_threshold => '1h', clean_expired_metadata => false)"
    )
    after_expire = snapshot_count(cat, identifier)
    assert 0 < after_expire <= after_optimize

    trino_exec(
        f"ALTER TABLE iceberg.{ns}.orders EXECUTE remove_orphan_files(retention_threshold => '1h')"
    )
    assert trino_scalar(f"SELECT count(*) FROM iceberg.{ns}.orders") == "3"
