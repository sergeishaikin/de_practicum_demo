from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa
import pytest

from medallion import iceberg_medallion as m
from tests.support.fakes import FakeCatalog, FakeMetrics, FakeTable
from tests.support import medallion_harness as h

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
    "business_version",
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
            "business_version": pa.array(
                [r[7] if len(r) > 7 else None for r in rows], type=pa.int64()
            ),
        }
    )


class TestBuildSilver:
    def test_dedup_latest_business_version_wins(self) -> None:
        df = bronze_table(
            [
                ("a", "c1", 10.0, "US", "paid", 0, 1, 1),
                ("a", "c2", 20.0, "US", "paid", 1, 5, 5),
                ("b", "c3", 30.0, "DE", "created", 2, 3, 3),
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

    def test_business_version_beats_transport_offset(self) -> None:
        silver = m.build_silver(
            bronze_table(
                [
                    ("a", "v5", 50.0, "US", "delivered", 0, 1, 5),
                    ("a", "v3", 30.0, "US", "shipped", 0, 99, 3),
                ]
            )
        )
        row = silver.to_pylist()[0]
        assert row["business_version"] == 5
        assert row["kafka_offset"] == 1
        assert row["customer"] == "v5"

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

    def test_null_amount_counted_with_nonpositive(self) -> None:
        # Regression: pc.or_ propagates the null produced by less_equal(None, 0),
        # silently dropping the null-amount violation. Must use Kleene OR.
        df = pa.table(
            {
                "order_id": ["a", "b", "c"],
                "amount": [None, -1.0, 5.0],
                "country": ["US", "US", "US"],
                "status": ["paid", "paid", "paid"],
                "event_time": [TS, TS, TS],
            }
        )
        assert m.run_quality_checks(df) == {"amount_null_or_nonpositive": 2}

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
        assert metrics.cycle()["status"] == "success"
        assert metrics.cycle()["source"] == "medallion"
        assert metrics.cycle()["bronze_rows"] == 3
        assert metrics.cycle()["silver_rows"] == 2
        assert metrics.cycle()["gold_rows"] == 2
        assert metrics.cycle()["duplicates_removed"] == 1
        assert metrics.cycle()["quality_violations"] == 0

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
        assert metrics.cycle()["status"] == "failed"
        assert metrics.cycle()["quality_violations"] == 1
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
            assert metrics.cycle()["status"] == "success"
            assert metrics.cycle()["quality_violations"] == 1
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


def marker_lines(captured: str) -> list[str]:
    """Every stdout line the cycle-complete marker owns."""

    return [
        line
        for line in captured.splitlines()
        if line.startswith(m.CYCLE_COMPLETE_MARKER)
    ]


def b2_lake(monkeypatch, *, gold_source: str = "legacy", shadow: bool = True):
    """A b2 deployment whose persisted Silver agrees with the legacy rebuild.

    Shadow comparison is fail-closed, so a cycle only completes when the two
    projections match; deriving persisted Silver from the same Bronze is the
    cheapest way to say "this deployment is healthy".
    """

    bronze_df = bronze_table([("a", "c1", 10.0, "US", "paid", 0, 1, 1)])
    catalog = FakeCatalog(
        {
            "bronze.orders": FakeTable(bronze_df),
            "silver.orders_clean": FakeTable(m.build_silver(bronze_df)),
            "gold.orders_daily_metrics": FakeTable(),
        }
    )
    monkeypatch.setattr(m, "run_b2", lambda *args, **kwargs: None)
    monkeypatch.setattr(m, "GOLD_SOURCE", gold_source)
    monkeypatch.setattr(m, "SHADOW_COMPARE_ENABLED", shadow)
    return catalog, FakeMetrics()


class TestCycleCompleteMarker:
    """The per-cycle stdout line the integration harness reads as liveness.

    The format is fixed here for the rest of the phase: a deployment that
    completed a cycle says so exactly once, and one that did not says nothing.
    """

    def test_marker_token_is_stable(self) -> None:
        assert m.CYCLE_COMPLETE_MARKER == "cycle-complete"

    def test_completed_b2_cycle_announces_itself_once(
        self, monkeypatch, capsys
    ) -> None:
        catalog, metrics = b2_lake(monkeypatch)

        m.run(catalog, metrics, "b2")

        lines = marker_lines(capsys.readouterr().out)
        assert len(lines) == 1
        fields = lines[0].split()
        assert fields[0] == m.CYCLE_COMPLETE_MARKER
        assert [field.split("=", 1)[0] for field in fields[1:]] == [
            "cycle_id",
            "gold",
            "shadow",
            "duration_ms",
        ]
        values = dict(field.split("=", 1) for field in fields[1:])
        assert values["cycle_id"] == metrics.cycle()["cycle_id"]
        assert values["gold"] == "rebuilt"
        assert values["shadow"] == "compared"

    def test_marker_duration_is_the_cycle_records_duration(
        self, monkeypatch, capsys
    ) -> None:
        catalog, metrics = b2_lake(monkeypatch)

        m.run(catalog, metrics, "b2")

        values = dict(
            field.split("=", 1)
            for field in marker_lines(capsys.readouterr().out)[0].split()[1:]
        )
        assert int(values["duration_ms"]) == metrics.cycle()["duration_ms"]

    def test_shadow_disabled_is_reported_as_disabled(self, monkeypatch, capsys) -> None:
        catalog, metrics = b2_lake(monkeypatch, shadow=False)

        m.run(catalog, metrics, "b2")

        values = dict(
            field.split("=", 1)
            for field in marker_lines(capsys.readouterr().out)[0].split()[1:]
        )
        assert values["shadow"] == "disabled"

    def test_completed_legacy_cycle_reports_a_rebuild_without_shadow(
        self, capsys
    ) -> None:
        catalog = FakeCatalog(
            {
                "bronze.orders": FakeTable(
                    bronze_table([("a", "c1", 10.0, "US", "paid", 0, 1)])
                )
            }
        )
        metrics = FakeMetrics()

        m.run(catalog, metrics)

        values = dict(
            field.split("=", 1)
            for field in marker_lines(capsys.readouterr().out)[0].split()[1:]
        )
        assert values["gold"] == "rebuilt"
        assert values["shadow"] == "disabled"
        assert values["cycle_id"] == metrics.cycle()["cycle_id"]
        assert int(values["duration_ms"]) == metrics.cycle()["duration_ms"]

    def test_shadow_mismatch_prints_no_marker(self, monkeypatch, capsys) -> None:
        catalog, metrics = b2_lake(monkeypatch)
        catalog.tables["silver.orders_clean"].df = m.build_silver(
            bronze_table([("a", "c1", 99.0, "US", "paid", 0, 1, 1)])
        )

        with pytest.raises(ValueError, match="Shadow comparison failed"):
            m.run(catalog, metrics, "b2")

        assert marker_lines(capsys.readouterr().out) == []

    def test_absent_bronze_prints_no_marker(self, capsys) -> None:
        m.run(FakeCatalog({}), FakeMetrics())

        assert marker_lines(capsys.readouterr().out) == []


class FakeProcess:
    """The slice of ``subprocess.Popen`` a ``CycleWatcher`` actually touches.

    Streams are plain iterables of lines, which is what the watcher's drain
    loop consumes from a real text-mode pipe as well. `returncode` of ``None``
    means "still running", matching ``Popen.poll``.
    """

    def __init__(
        self,
        stdout: list[str],
        stderr: list[str] | None = None,
        returncode: int | None = None,
    ) -> None:
        self.stdout = list(stdout)
        self.stderr = list(stderr or [])
        self._returncode = returncode

    def poll(self) -> int | None:
        return self._returncode


def cycle_line(**overrides: str) -> str:
    fields = {
        "cycle_id": "ab12",
        "gold": "rebuilt",
        "shadow": "compared",
        "duration_ms": "1234",
    }
    fields.update(overrides)
    return (
        f"{m.CYCLE_COMPLETE_MARKER} "
        + " ".join(f"{key}={value}" for key, value in fields.items())
        + "\n"
    )


class TestParseCycleMarker:
    """The harness's reader for the marker `run()` prints.

    These prove the parsing contract without a stack. What they deliberately do
    *not* prove is that a real medallion subprocess emits the marker down a real
    pipe — that is the live layer's job, and `ci-m5-gates.yml` runs it on the PR.
    """

    def test_well_formed_line_yields_every_field(self) -> None:
        assert h.parse_cycle_marker(
            "cycle-complete cycle_id=ab12 gold=rebuilt "
            "shadow=compared duration_ms=1234"
        ) == {
            "cycle_id": "ab12",
            "gold": "rebuilt",
            "shadow": "compared",
            "duration_ms": 1234,
        }

    def test_duration_is_coerced_to_an_int(self) -> None:
        assert h.parse_cycle_marker(cycle_line(duration_ms="0"))["duration_ms"] == 0

    @pytest.mark.parametrize(
        ("line", "why"),
        [
            ("", "an empty line"),
            ("\n", "a blank line"),
            ("Gold gold.orders: overwritten with 2 daily metrics", "an ordinary log"),
            (
                "Medallion error: cycle-complete cycle_id=ab12 gold=rebuilt "
                "shadow=compared duration_ms=1234",
                "a line that only quotes the marker",
            ),
            (
                "cycle-complete cycle_id=ab12 gold rebuilt "
                "shadow=compared duration_ms=1234",
                "a field with no value",
            ),
            (
                "cycle-complete cycle_id=ab12 gold=rebuilt shadow=compared",
                "a missing field",
            ),
            (
                "cycle-complete cycle_id=ab12 gold=rebuilt "
                "shadow=compared duration_ms=fast",
                "a non-integer duration",
            ),
            (
                "cycle-complete cycle_id=ab12 gold=rebuilt shadow=compared "
                "duration_ms=1234 extra=1",
                "an unknown field",
            ),
        ],
    )
    def test_anything_else_is_not_a_marker(self, line: str, why: str) -> None:
        assert h.parse_cycle_marker(line) is None, why


class TestCycleWatcher:
    def test_returns_the_announced_cycle(self) -> None:
        watcher = h.CycleWatcher(FakeProcess([cycle_line()]))
        try:
            assert watcher.wait_for_cycle_complete(timeout=5) == {
                "cycle_id": "ab12",
                "gold": "rebuilt",
                "shadow": "compared",
                "duration_ms": 1234,
            }
        finally:
            watcher.close()

    def test_silence_raises_with_both_pipes_quoted(self) -> None:
        watcher = h.CycleWatcher(
            FakeProcess(
                ["Bronze table not available yet; skipping cycle\n"],
                stderr=["Medallion error: boom\n"],
            )
        )
        try:
            with pytest.raises(AssertionError) as failure:
                watcher.wait_for_cycle_complete(timeout=0.2)
        finally:
            watcher.close()
        message = str(failure.value)
        assert "Bronze table not available yet" in message
        assert "Medallion error: boom" in message

    def test_a_non_matching_decision_does_not_satisfy_the_wait(self) -> None:
        watcher = h.CycleWatcher(
            FakeProcess([cycle_line(), cycle_line(cycle_id="cd34", gold="skipped")])
        )
        try:
            marker = watcher.wait_for_cycle_complete(timeout=5, gold="skipped")
        finally:
            watcher.close()
        assert marker["cycle_id"] == "cd34"

    def test_a_dead_deployment_fails_without_waiting_out_the_timeout(self) -> None:
        watcher = h.CycleWatcher(
            FakeProcess([], stderr=["Unsupported rollout state\n"], returncode=1)
        )
        try:
            with pytest.raises(AssertionError, match="exited with 1"):
                watcher.wait_for_cycle_complete(timeout=30)
        finally:
            watcher.close()
