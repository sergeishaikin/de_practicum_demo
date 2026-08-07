from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa
import pytest
from pyiceberg.exceptions import NoSuchTableError

from medallion import iceberg_medallion as m

TS = datetime(2026, 1, 1, 12, 0, 0)
EVENT_DATE = date(2026, 1, 1)

SILVER_COLUMNS = [
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


def bronze_table(rows: list[tuple]) -> pa.Table:
    return pa.table(
        {
            "order_id": pa.array([r[0] for r in rows], type=pa.string()),
            "customer": pa.array([r[1] for r in rows], type=pa.string()),
            "amount": pa.array([r[2] for r in rows], type=pa.float64()),
            "country": pa.array([r[3] for r in rows], type=pa.string()),
            "status": pa.array([r[4] for r in rows], type=pa.string()),
            "event_time": pa.array([TS] * len(rows), type=pa.timestamp("us")),
            "kafka_timestamp": pa.array([TS] * len(rows), type=pa.timestamp("us")),
            "kafka_partition": pa.array([r[5] for r in rows], type=pa.int32()),
            "kafka_offset": pa.array([r[6] for r in rows], type=pa.int64()),
            "event_date": pa.array([EVENT_DATE] * len(rows), type=pa.date32()),
        }
    )


class FakeScan:
    def __init__(self, df: pa.Table) -> None:
        self.df = df

    def to_arrow(self) -> pa.Table:
        return self.df


class FakeTable:
    def __init__(self, df: pa.Table | None = None) -> None:
        self.df = df

    @property
    def num_rows(self) -> int:
        return 0 if self.df is None else self.df.num_rows

    def scan(self) -> FakeScan:
        return FakeScan(self.df)

    def overwrite(self, df: pa.Table) -> None:
        self.df = df


class FakeCatalog:
    def __init__(self, tables: dict[str, FakeTable] | None = None) -> None:
        self.tables = tables or {}

    def load_table(self, identifier: str) -> FakeTable:
        if identifier not in self.tables:
            raise NoSuchTableError(f"no table {identifier}")
        return self.tables[identifier]

    def create_namespace_if_not_exists(self, namespace: str) -> None:
        pass

    def create_table(self, identifier: str, **kwargs) -> FakeTable:
        table = FakeTable(None)
        self.tables[identifier] = table
        return table


class FakeMetrics:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


class TestBuildSilver:
    def test_dedup_latest_offset_wins(self) -> None:
        df = bronze_table(
            [
                ("a", "c1", 10.0, "US", "paid", 0, 1),
                ("a", "c2", 20.0, "US", "paid", 1, 5),
                ("b", "c3", 30.0, "DE", "created", 2, 3),
            ]
        )
        silver = m.build_silver(df)
        assert silver.num_rows == 2
        rows = silver.select(["order_id", "kafka_offset", "customer"]).to_pydict()
        assert rows["order_id"] == ["a", "b"]
        assert rows["kafka_offset"] == [5, 3]
        assert rows["customer"] == ["c2", "c3"]

    def test_no_duplicates_passthrough(self) -> None:
        df = bronze_table(
            [
                ("a", "c1", 10.0, "US", "paid", 0, 1),
                ("b", "c2", 20.0, "US", "created", 1, 2),
            ]
        )
        silver = m.build_silver(df)
        assert silver.num_rows == 2

    def test_output_column_order_is_silver_schema(self) -> None:
        df = bronze_table([("a", "c1", 10.0, "US", "paid", 0, 1)])
        silver = m.build_silver(df)
        assert silver.column_names == SILVER_COLUMNS

    def test_empty_table(self) -> None:
        silver = m.build_silver(bronze_table([]))
        assert silver.num_rows == 0
        assert silver.column_names == SILVER_COLUMNS

    def test_handles_all_null_event_time(self) -> None:
        df = pa.table(
            {
                "order_id": ["a", "b"],
                "customer": ["c1", "c2"],
                "amount": [10.0, 20.0],
                "country": ["US", "US"],
                "status": ["paid", "paid"],
                "event_time": [None, None],
                "kafka_timestamp": [None, None],
                "kafka_partition": [0, 1],
                "kafka_offset": [1, 2],
                "event_date": [EVENT_DATE, EVENT_DATE],
            }
        )
        assert pa.types.is_null(df.schema.field("event_time").type)
        silver = m.build_silver(df)
        assert silver.num_rows == 2
        assert pa.types.is_timestamp(silver.schema.field("event_time").type)

    def test_handles_all_null_sort_and_hash_columns(self) -> None:
        df = pa.table(
            {
                "order_id": ["a", "a"],
                "customer": ["c1", "c2"],
                "amount": [10.0, 20.0],
                "country": ["US", "US"],
                "status": ["paid", "paid"],
                "event_time": [TS, TS],
                "kafka_timestamp": [TS, TS],
                "kafka_partition": [0, 1],
                "kafka_offset": [None, None],
                "event_date": [None, None],
            }
        )
        silver = m.build_silver(df)
        assert silver.num_rows == 1
        assert pa.types.is_int64(silver.schema.field("kafka_offset").type)
        assert pa.types.is_date32(silver.schema.field("event_date").type)


class TestBuildGold:
    def test_aggregation_counts_sums(self) -> None:
        silver = m.build_silver(
            bronze_table(
                [
                    ("a", "cust1", 10.0, "US", "paid", 0, 1),
                    ("b", "cust2", 20.0, "US", "paid", 1, 2),
                    ("c", "cust3", 30.0, "US", "created", 2, 3),
                    ("d", "cust4", 40.0, "DE", "paid", 3, 4),
                ]
            )
        )
        gold = m.build_gold(silver)
        rows = gold.to_pydict()
        by = {
            (rows["event_date"][i], rows["country"][i], rows["status"][i]): (
                rows["orders_count"][i],
                rows["total_amount"][i],
                rows["avg_amount"][i],
                rows["distinct_customers"][i],
            )
            for i in range(gold.num_rows)
        }
        assert by[(EVENT_DATE, "US", "paid")] == (2, 30.0, 15.0, 2)
        assert by[(EVENT_DATE, "US", "created")] == (1, 30.0, 30.0, 1)
        assert by[(EVENT_DATE, "DE", "paid")] == (1, 40.0, 40.0, 1)

    def test_distinct_customers(self) -> None:
        silver = m.build_silver(
            bronze_table(
                [
                    ("a", "cust1", 10.0, "US", "paid", 0, 1),
                    ("b", "cust1", 20.0, "US", "paid", 1, 2),
                ]
            )
        )
        gold = m.build_gold(silver)
        assert gold.to_pydict()["distinct_customers"] == [1]

    def test_empty_table(self) -> None:
        gold = m.build_gold(bronze_table([]))
        assert gold.num_rows == 0
        assert gold.column_names == [
            "event_date",
            "country",
            "status",
            "orders_count",
            "total_amount",
            "avg_amount",
            "distinct_customers",
        ]


class TestRunQualityChecks:
    def test_flags_every_violation(self) -> None:
        df = pa.table(
            {
                "order_id": [None, "x"],
                "amount": [-1.0, 5.0],
                "country": ["US", None],
                "status": ["bad", "paid"],
                "event_time": [None, TS],
            }
        )
        assert m.run_quality_checks(df) == {
            "order_id_null": 1,
            "amount_null_or_nonpositive": 1,
            "country_null": 1,
            "status_invalid": 1,
            "event_time_null": 1,
        }

    def test_clean_rows_no_violations(self) -> None:
        df = pa.table(
            {
                "order_id": ["x"],
                "amount": [5.0],
                "country": ["US"],
                "status": ["paid"],
                "event_time": [TS],
            }
        )
        assert m.run_quality_checks(df) == {}

    def test_missing_column_is_skipped(self) -> None:
        df = pa.table({"order_id": [None]})
        assert m.run_quality_checks(df) == {"order_id_null": 1}


class TestRun:
    def test_success_overwrites_and_records(self) -> None:
        catalog = FakeCatalog(
            {
                "bronze.orders": FakeTable(
                    bronze_table(
                        [
                            ("a", "c1", 10.0, "US", "paid", 0, 1),
                            ("a", "c2", 20.0, "US", "paid", 1, 5),
                            ("b", "c3", 30.0, "DE", "created", 2, 3),
                        ]
                    )
                )
            }
        )
        metrics = FakeMetrics()
        m.run(catalog, metrics)
        silver = catalog.tables["silver.orders_clean"].df
        gold = catalog.tables["gold.orders_daily_metrics"].df
        assert silver.num_rows == 2
        assert gold.num_rows == 2
        assert metrics.records[-1]["status"] == "success"
        assert metrics.records[-1]["source"] == "medallion"
        assert metrics.records[-1]["bronze_rows"] == 3
        assert metrics.records[-1]["silver_rows"] == 2
        assert metrics.records[-1]["gold_rows"] == 2
        assert metrics.records[-1]["duplicates_removed"] == 1
        assert metrics.records[-1]["quality_violations"] == 0

    def test_bronze_missing_skips_cycle(self) -> None:
        metrics = FakeMetrics()
        m.run(FakeCatalog({}), metrics)
        assert metrics.records == []

    def test_fail_on_violations_aborts(self, monkeypatch) -> None:
        monkeypatch.setattr(m, "FAIL_ON_VIOLATIONS", True)
        catalog = FakeCatalog(
            {
                "bronze.orders": FakeTable(
                    pa.table(
                        {
                            "order_id": [None, "b"],
                            "customer": ["c1", "c2"],
                            "amount": [10.0, 20.0],
                            "country": ["US", "US"],
                            "status": ["paid", "paid"],
                            "event_time": [TS, TS],
                            "kafka_timestamp": [TS, TS],
                            "kafka_partition": [0, 1],
                            "kafka_offset": [1, 2],
                            "event_date": [EVENT_DATE, EVENT_DATE],
                        }
                    )
                )
            }
        )
        metrics = FakeMetrics()
        m.run(catalog, metrics)
        assert metrics.records[-1]["status"] == "failed"
        assert metrics.records[-1]["quality_violations"] == 1
        assert "silver.orders_clean" not in catalog.tables

    def test_violations_recorded_but_proceeds_when_not_fatal(self) -> None:
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(m, "FAIL_ON_VIOLATIONS", False)
        try:
            catalog = FakeCatalog(
                {
                    "bronze.orders": FakeTable(
                        pa.table(
                            {
                                "order_id": [None, "b"],
                                "customer": ["c1", "c2"],
                                "amount": [10.0, 20.0],
                                "country": ["US", "US"],
                                "status": ["paid", "paid"],
                                "event_time": [TS, TS],
                                "kafka_timestamp": [TS, TS],
                                "kafka_partition": [0, 1],
                                "kafka_offset": [1, 2],
                                "event_date": [EVENT_DATE, EVENT_DATE],
                            }
                        )
                    )
                }
            )
            metrics = FakeMetrics()
            m.run(catalog, metrics)
            assert metrics.records[-1]["status"] == "success"
            assert metrics.records[-1]["quality_violations"] == 1
            assert catalog.tables["silver.orders_clean"].df.num_rows == 2
        finally:
            monkeypatch.undo()


class TestCatalogAndMain:
    def test_get_catalog_returns_rest_catalog(self, monkeypatch) -> None:
        class FakeRestCatalog:
            def __init__(self, name: str, **kwargs) -> None:
                self.name = name
                self.kwargs = kwargs

        monkeypatch.setattr(m, "RestCatalog", FakeRestCatalog)
        cat = m.get_catalog()
        assert isinstance(cat, FakeRestCatalog)
        assert cat.name == "default"
        assert cat.kwargs["s3.endpoint"] == m.S3_ENDPOINT

    def test_main_loop_handles_run_errors(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(m, "Metrics", lambda: FakeMetrics())
        monkeypatch.setattr(m, "get_catalog", lambda: object())
        calls = {"n": 0}

        def fake_run(catalog, metrics) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            raise SystemExit()

        monkeypatch.setattr(m, "run", fake_run)
        monkeypatch.setattr(m.time, "sleep", lambda s: None)
        with pytest.raises(SystemExit):
            m.main()
        assert calls["n"] == 2
        assert "Medallion error: boom" in capsys.readouterr().err
