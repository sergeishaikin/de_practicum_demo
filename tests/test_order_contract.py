from __future__ import annotations

from pathlib import Path

from pyiceberg.types import LongType

from medallion import iceberg_medallion as medallion
from writer import iceberg_writer as writer


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_iceberg_contracts_declare_business_version() -> None:
    assert isinstance(writer.TABLE_SCHEMA.find_field("business_version").field_type, LongType)
    assert isinstance(
        medallion.SILVER_SCHEMA.find_field("business_version").field_type,
        LongType,
    )


def test_producer_and_spark_contracts_emit_business_version() -> None:
    producer_source = (
        REPO_ROOT / "kafka" / "producer" / "orders_producer.py"
    ).read_text(encoding="utf-8")
    spark_source = (
        REPO_ROOT / "spark" / "jobs" / "orders_streaming.py"
    ).read_text(encoding="utf-8")

    assert '"business_version": 1' in producer_source
    assert 'StructField("business_version", LongType()' in spark_source
    assert "business_version bigint" in spark_source
    assert "order by business_version desc nulls last, kafka_offset desc" in spark_source


class EvolvingSchema:
    column_names = ["order_id"]


class EvolvingUpdate:
    def __init__(self, table: "EvolvingTable") -> None:
        self.table = table
        self.added: list[tuple[str, object]] = []

    def add_column(self, name: str, field_type, **kwargs):
        del kwargs
        self.added.append((name, field_type))
        return self

    def commit(self) -> None:
        self.table.schema_obj.column_names.append("business_version")
        self.table.committed = True


class EvolvingTable:
    def __init__(self) -> None:
        self.schema_obj = EvolvingSchema()
        self.committed = False
        self.update = EvolvingUpdate(self)

    def schema(self) -> EvolvingSchema:
        return self.schema_obj

    def update_schema(self) -> EvolvingUpdate:
        return self.update


class EvolvingCatalog:
    def __init__(self, table: EvolvingTable) -> None:
        self.table = table

    def create_namespace_if_not_exists(self, namespace: str) -> None:
        del namespace

    def load_table(self, identifier: str) -> EvolvingTable:
        del identifier
        return self.table


def test_existing_bronze_table_gets_additive_business_version_evolution() -> None:
    table = EvolvingTable()
    writer.ensure_table(EvolvingCatalog(table))

    assert table.committed is True
    assert table.update.added == [("business_version", LongType())]
