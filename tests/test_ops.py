from __future__ import annotations

import prometheus_client
import pytest

from common import ops

OBSERVATION = {
    "source": "medallion",
    "status": "success",
    "rows_processed": 7,
    "files_processed": 2,
    "keys_processed": 3,
    "duration_ms": 1500,
    "work_available": 4,
    "work_in_flight": 1,
    "work_completed": 9,
    "lower_versions_ignored": 2,
    "ff14_conflicts": 1,
    "shadow_mismatches": 3,
    "silver_duration_ms": 250,
    "gold_duration_ms": 750,
    "files_planned": 11,
    "files_removed": 5,
    "files_added": 6,
    "bytes_planned": 1024,
    "bytes_removed": 256,
    "bytes_added": 512,
}


def published(collector, name: str, **labels: str) -> float:
    """Read one published sample straight out of a Prometheus collector.

    Asserting on collected samples rather than on call counts proves the value
    an operator's dashboard would actually see, including the label set it is
    filed under.
    """

    for metric in collector.collect():
        for sample in metric.samples:
            if sample.name == name and sample.labels == labels:
                return sample.value
    raise AssertionError(f"no sample {name} with labels {labels}")


class FakeCursor:
    def __init__(self, log: list) -> None:
        self.log = log

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.log.append((sql, params))


class FakeConn:
    closed = 0

    def __init__(self, log: list) -> None:
        self.log = log
        self.autocommit = False
        self.close_called = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.log)

    def close(self) -> None:
        self.closed = 1
        self.close_called = True


class FakePsycopg2:
    def __init__(self, log: list, raise_on_connect: Exception | None = None) -> None:
        self.log = log
        self.raise_on_connect = raise_on_connect
        self.connect_kw: dict | None = None
        self.conn: FakeConn | None = None

    def connect(self, **kwargs) -> FakeConn:
        self.connect_kw = kwargs
        if self.raise_on_connect is not None:
            raise self.raise_on_connect
        self.conn = FakeConn(self.log)
        return self.conn


class TestPgConnParams:
    def test_returns_env_values(self, monkeypatch) -> None:
        monkeypatch.setattr(ops, "POSTGRES_HOST", "pg")
        monkeypatch.setattr(ops, "POSTGRES_PORT", 6543)
        monkeypatch.setattr(ops, "POSTGRES_DB", "db")
        monkeypatch.setattr(ops, "POSTGRES_USER", "user")
        monkeypatch.setattr(ops, "POSTGRES_PASSWORD", "pass")
        assert ops.pg_conn_params() == {
            "host": "pg",
            "port": 6543,
            "dbname": "db",
            "user": "user",
            "password": "pass",
        }


def inserted_row(log, index: int = 1) -> dict:
    """Map a captured insert's parameters onto the column names in its own SQL.

    Positional assertions on the parameter tuple were the previous idiom. They
    are length-sensitive and index-shifting: adding one column to the statement
    silently moves every later value, so a test could keep passing while
    asserting the wrong thing. Reading the column list out of the statement
    itself makes the assertion say what it means, and survives additive schema
    evolution.

    The length check is the load-bearing part. It proves the statement's column
    list and its parameter tuple still agree, which is exactly the failure a
    column added without a matching parameter would otherwise cause.
    """

    sql, params = log[index][0], log[index][1]
    marker = "insert into marts.lakehouse_metrics"
    assert marker in sql, f"entry {index} is not a lakehouse_metrics insert: {sql!r}"
    columns_text = sql.split(marker, 1)[1].split("(", 1)[1].split(")", 1)[0]
    names = [name.strip() for name in columns_text.split(",") if name.strip()]
    # metric_ts is supplied by now() inside the statement, not as a parameter.
    assert names[0] == "metric_ts", names[:1]
    names = names[1:]
    assert len(names) == len(params), (
        f"insert column list and parameter tuple disagree: "
        f"{len(names)} columns {names} vs {len(params)} params {params}"
    )
    return dict(zip(names, params))


class TestMetrics:
    def test_disabled_noop(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(ops, "psycopg2", FakePsycopg2([]))
        m = ops.Metrics()
        m.enabled = False
        m.record(source="writer", status="success")
        assert m.conn is None

    def test_record_inserts_row_and_ensures_schema_once(self, monkeypatch) -> None:
        log: list = []
        fake = FakePsycopg2(log)
        monkeypatch.setattr(ops, "psycopg2", fake)
        m = ops.Metrics()
        m.enabled = True
        m.record(source="writer", status="success", load_id="L1", rows_processed=3)
        assert fake.connect_kw == ops.pg_conn_params()
        ddl_sql, insert_sql = log[0][0], log[1][0]
        assert ddl_sql.strip().startswith("create table if not exists")
        assert "insert into marts.lakehouse_metrics" in insert_sql
        row = inserted_row(log)
        assert row["source"] == "writer"
        assert row["load_id"] == "L1"
        assert row["status"] == "success"
        assert row["rows_processed"] == 3
        # Every remaining *counter* column defaults to 0. The cycle-identity
        # columns are deliberately excluded: they are nullable-with-no-default so
        # that `cycle_id IS NULL` separates the pre-Phase-4 era, and they carry
        # their own assertions in test_record_defaults_leave_cycle_identity_null.
        identity = {
            "cycle_id",
            "phase",
            "bronze_snapshot_id",
            "silver_snapshot_id",
            "gold_snapshot_id",
            "shadow_skipped",
            "gold_skipped",
        }
        counters = {
            name: value
            for name, value in row.items()
            if name not in {"source", "load_id", "status", "rows_processed"} | identity
        }
        assert set(counters.values()) == {0}, counters
        assert m.schema_ready is True
        m.record(source="writer", status="success")
        assert len(log) == 3  # one more insert, no extra DDL

    def test_record_is_best_effort_on_db_failure(self, monkeypatch, capsys) -> None:
        fake = FakePsycopg2([], raise_on_connect=RuntimeError("down"))
        monkeypatch.setattr(ops, "psycopg2", fake)
        m = ops.Metrics()
        m.enabled = True
        m.record(source="writer", status="error")
        assert m.conn is None
        assert "Metrics write failed (writer)" in capsys.readouterr().err

    def test_record_swallows_cursor_errors(self, monkeypatch, capsys) -> None:
        class BoomCursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                raise RuntimeError("syntax error")

        class BoomConn:
            closed = 0
            autocommit = False

            def cursor(self):
                return BoomCursor()

        class BoomPg:
            def connect(self, **kwargs):
                return BoomConn()

        monkeypatch.setattr(ops, "psycopg2", BoomPg())
        m = ops.Metrics()
        m.enabled = True
        m.record(source="medallion", status="failed")
        assert "Metrics write failed (medallion)" in capsys.readouterr().err

    def test_record_defaults_leave_cycle_identity_null(self, monkeypatch) -> None:
        """Pre-Phase-4 rows and writer rows must stay separable by `cycle_id IS NULL`.

        A default of `''` or `'unknown'` would let an un-instrumented run
        masquerade as an instrumented one, which is exactly what the historical
        interpretation rule depends on being impossible.
        """

        log: list = []
        monkeypatch.setattr(ops, "psycopg2", FakePsycopg2(log))
        m = ops.Metrics()
        m.enabled = True
        m.record(source="writer", status="success")

        row = inserted_row(log)
        assert row["cycle_id"] is None
        assert row["phase"] is None
        assert row["bronze_snapshot_id"] is None
        assert row["silver_snapshot_id"] is None
        assert row["gold_snapshot_id"] is None
        assert row["shadow_skipped"] is False
        assert row["gold_skipped"] is False

    def test_record_persists_cycle_identity_when_supplied(self, monkeypatch) -> None:
        log: list = []
        monkeypatch.setattr(ops, "psycopg2", FakePsycopg2(log))
        m = ops.Metrics()
        m.enabled = True
        m.record(
            source="medallion",
            status="success",
            cycle_id="abc",
            phase="b2",
            bronze_snapshot_id=11,
            silver_snapshot_id=22,
            gold_snapshot_id=33,
            shadow_skipped=True,
            gold_skipped=True,
        )

        row = inserted_row(log)
        assert row["cycle_id"] == "abc"
        assert row["phase"] == "b2"
        assert row["bronze_snapshot_id"] == 11
        assert row["silver_snapshot_id"] == 22
        assert row["gold_snapshot_id"] == 33
        assert row["shadow_skipped"] is True
        assert row["gold_skipped"] is True

    def test_record_persists_m5_observability_dimensions(self, monkeypatch) -> None:
        log: list = []
        fake = FakePsycopg2(log)
        monkeypatch.setattr(ops, "psycopg2", fake)
        m = ops.Metrics()
        m.enabled = True
        m.record(
            source="medallion",
            status="success",
            work_available=2,
            work_in_flight=0,
            work_completed=4,
            keys_processed=3,
            lower_versions_ignored=1,
            ff14_conflicts=0,
            shadow_comparisons=1,
            shadow_mismatches=0,
            silver_duration_ms=11,
            gold_duration_ms=7,
        )
        row = inserted_row(log)
        assert row["work_available"] == 2
        assert row["work_in_flight"] == 0
        assert row["work_completed"] == 4
        assert row["keys_processed"] == 3
        assert row["lower_versions_ignored"] == 1
        assert row["ff14_conflicts"] == 0
        assert row["shadow_comparisons"] == 1
        assert row["shadow_mismatches"] == 0
        assert row["silver_duration_ms"] == 11
        assert row["gold_duration_ms"] == 7

    def test_close(self, monkeypatch) -> None:
        fake = FakePsycopg2([])
        monkeypatch.setattr(ops, "psycopg2", fake)
        m = ops.Metrics()
        m.enabled = True
        m.record(source="writer", status="success")
        m.close()
        assert fake.conn.close_called is True
        assert m.conn is None

    def test_close_swallows_close_errors(self) -> None:
        class BoomCloseConn:
            closed = 1

            def close(self) -> None:
                raise RuntimeError("close boom")

        m = ops.Metrics()
        m.conn = BoomCloseConn()
        m.close()
        assert m.conn is None

    def test_close_without_connection(self) -> None:
        m = ops.Metrics()
        m.enabled = False
        m.close()
        assert m.conn is None


@pytest.fixture
def served(monkeypatch) -> list:
    """Capture the endpoint that would be served, without binding a port."""

    calls: list = []
    monkeypatch.setattr(
        prometheus_client,
        "start_http_server",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    return calls


class TestClassifyMetricRow:
    """The historical interpretation rule, executable rather than prose.

    Making it a function is the point: a documented rule drifts silently, a
    tested one cannot.
    """

    def test_pre_era_success_with_gold_duration_is_an_outer_cycle(self) -> None:
        assert (
            ops.classify_metric_row(status="success", gold_duration_ms=4130) == "cycle"
        )

    def test_pre_era_success_without_gold_duration_is_nested_b2(self) -> None:
        assert ops.classify_metric_row(status="success", gold_duration_ms=0) == "b2"

    def test_shadow_failed_is_an_outer_cycle_not_a_nested_metric(self) -> None:
        """The row the naive gold_duration_ms rule gets wrong.

        _run_m4 raises before Gold, so it never sets gold_duration_ms -- but it
        is an outer cycle that aborted, and misfiling the safety-critical row as
        nested detail is exactly the failure this rule exists to prevent.
        """

        assert (
            ops.classify_metric_row(status="shadow_failed", gold_duration_ms=0)
            == "cycle"
        )

    def test_failed_is_nested_without_claiming_which_emitter(self) -> None:
        """`failed` comes from run_b2 or _legacy_silver_cycle; we cannot tell."""

        assert ops.classify_metric_row(status="failed", gold_duration_ms=0) == "nested"

    def test_unrecognised_status_does_not_raise(self) -> None:
        assert (
            ops.classify_metric_row(status="something-legacy", gold_duration_ms=0)
            == "unknown"
        )

    def test_phase_4_row_is_classified_from_its_own_phase(self) -> None:
        """A row that says what it is must not be second-guessed.

        Status and gold_duration_ms here would imply "b2" under the pre-era rule;
        the explicit phase must win.
        """

        assert (
            ops.classify_metric_row(
                status="success", gold_duration_ms=0, cycle_id="c1", phase="cycle"
            )
            == "cycle"
        )

    def test_phase_4_row_with_unknown_phase_is_unknown(self) -> None:
        for phase in (None, "not-a-phase"):
            assert (
                ops.classify_metric_row(
                    status="success", gold_duration_ms=0, cycle_id="c1", phase=phase
                )
                == "unknown"
            )


class TestCycleOnlyObservation:
    """A nested phase record is durable in PostgreSQL but must not reach Prometheus.

    The gauges are labelled by `source` alone, so before this guard the outer
    record overwrote the nested record's values with zeros seconds after they
    were measured. That reset lakehouse_files{kind="planned"}, lakehouse_bytes
    and lakehouse_work{state="in_flight"}, weakening LakehouseUnresolvedWork.
    """

    def _metrics(self, monkeypatch, log):
        monkeypatch.setattr(ops, "psycopg2", FakePsycopg2(log))
        m = ops.Metrics()
        m.enabled = True
        m.runtime = ops._RuntimeMetrics("9099")
        return m

    def test_phase_record_publishes_nothing(self, monkeypatch, served) -> None:
        log: list = []
        m = self._metrics(monkeypatch, log)

        m.record(source="medallion", status="success", phase="b2", cycle_id="c1")

        # It reached the durable sink...
        assert inserted_row(log)["phase"] == "b2"
        # ...and nowhere near a collector.
        with pytest.raises(AssertionError):
            published(
                m.runtime.events,
                "lakehouse_events_total",
                source="medallion",
                status="success",
            )

    def test_cycle_record_publishes_every_dimension(self, monkeypatch, served) -> None:
        m = self._metrics(monkeypatch, [])

        m.record(
            source="medallion",
            status="success",
            phase="cycle",
            cycle_id="c1",
            files_planned=7,
        )

        assert (
            published(
                m.runtime.events,
                "lakehouse_events_total",
                source="medallion",
                status="success",
            )
            == 1.0
        )
        assert (
            published(
                m.runtime.files, "lakehouse_files", source="medallion", kind="planned"
            )
            == 7.0
        )

    def test_one_cycle_counts_once_and_keeps_its_gauge(
        self, monkeypatch, served
    ) -> None:
        """The regression this guard exists for, stated as a test."""

        m = self._metrics(monkeypatch, [])

        m.record(
            source="medallion",
            status="success",
            phase="b2",
            cycle_id="c1",
            files_planned=7,
        )
        m.record(
            source="medallion",
            status="success",
            phase="cycle",
            cycle_id="c1",
            files_planned=7,
        )

        assert (
            published(
                m.runtime.events,
                "lakehouse_events_total",
                source="medallion",
                status="success",
            )
            == 1.0
        )
        # Previously the outer record reset this to 0 after the nested one set it.
        assert (
            published(
                m.runtime.files, "lakehouse_files", source="medallion", kind="planned"
            )
            == 7.0
        )


class TestRuntimeMetrics:
    @pytest.mark.parametrize("port", [None, ""])
    def test_absent_port_disables_runtime_before_any_collector_is_built(
        self, port
    ) -> None:
        runtime = ops._RuntimeMetrics(port)

        assert runtime.enabled is False
        assert not hasattr(runtime, "events")
        # The guard precedes every value lookup, so an empty observation is safe.
        assert runtime.observe() is None

    def test_enabled_runtime_serves_a_private_registry_on_the_configured_port(
        self, served
    ) -> None:
        runtime = ops._RuntimeMetrics("9099")

        assert runtime.enabled is True
        ((args, kwargs),) = served
        assert args == (9099,)
        assert kwargs["addr"] == "0.0.0.0"
        assert isinstance(kwargs["registry"], prometheus_client.CollectorRegistry)
        assert kwargs["registry"] is not prometheus_client.REGISTRY

    def test_a_second_runtime_does_not_collide_on_the_global_registry(
        self, served
    ) -> None:
        first = ops._RuntimeMetrics("9099")
        second = ops._RuntimeMetrics("9100")

        # A shared registry would reject the duplicate timeseries and silently
        # disable the second process's endpoint.
        assert (first.enabled, second.enabled) == (True, True)
        assert len(served) == 2

    def test_observe_publishes_every_runtime_dimension(self, served) -> None:
        runtime = ops._RuntimeMetrics("9099")

        runtime.observe(**OBSERVATION)

        assert published(runtime.up, "lakehouse_up", source="medallion") == 1
        assert (
            published(
                runtime.events,
                "lakehouse_events_total",
                source="medallion",
                status="success",
            )
            == 1
        )
        assert {
            state: published(
                runtime.work, "lakehouse_work", source="medallion", state=state
            )
            for state in ("available", "in_flight", "completed")
        } == {"available": 4, "in_flight": 1, "completed": 9}
        assert {
            kind: published(
                runtime.processed, "lakehouse_processed", source="medallion", kind=kind
            )
            for kind in ("rows", "files", "keys")
        } == {"rows": 7, "files": 2, "keys": 3}
        assert {
            kind: published(
                runtime.correctness,
                "lakehouse_correctness_total",
                source="medallion",
                kind=kind,
            )
            for kind in (
                "lower_versions_ignored",
                "ff14_conflicts",
                "shadow_mismatches",
            )
        } == {
            "lower_versions_ignored": 2,
            "ff14_conflicts": 1,
            "shadow_mismatches": 3,
        }
        assert {
            kind: published(
                runtime.files, "lakehouse_files", source="medallion", kind=kind
            )
            for kind in ("planned", "removed", "added")
        } == {"planned": 11, "removed": 5, "added": 6}
        assert {
            kind: published(
                runtime.bytes, "lakehouse_bytes", source="medallion", kind=kind
            )
            for kind in ("planned", "removed", "added")
        } == {"planned": 1024, "removed": 256, "added": 512}

    def test_durations_are_published_in_seconds(self, served) -> None:
        runtime = ops._RuntimeMetrics("9099")

        runtime.observe(**OBSERVATION)

        assert (
            published(
                runtime.duration, "lakehouse_duration_seconds_sum", source="medallion"
            )
            == 1.5
        )
        assert (
            published(
                runtime.duration, "lakehouse_duration_seconds_count", source="medallion"
            )
            == 1
        )
        assert {
            stage: published(
                runtime.stage_duration,
                "lakehouse_stage_duration_seconds",
                source="medallion",
                stage=stage,
            )
            for stage in ("silver", "gold")
        } == {"silver": 0.25, "gold": 0.75}

    def test_counters_accumulate_while_gauges_hold_the_latest_cycle(
        self, served
    ) -> None:
        runtime = ops._RuntimeMetrics("9099")

        runtime.observe(**OBSERVATION)
        runtime.observe(
            **{**OBSERVATION, "rows_processed": 1, "lower_versions_ignored": 5}
        )

        assert (
            published(
                runtime.events,
                "lakehouse_events_total",
                source="medallion",
                status="success",
            )
            == 2
        )
        assert (
            published(
                runtime.correctness,
                "lakehouse_correctness_total",
                source="medallion",
                kind="lower_versions_ignored",
            )
            == 7
        )
        assert (
            published(
                runtime.processed,
                "lakehouse_processed",
                source="medallion",
                kind="rows",
            )
            == 1
        )

    def test_last_event_records_the_observation_wall_clock(
        self, served, monkeypatch
    ) -> None:
        runtime = ops._RuntimeMetrics("9099")
        monkeypatch.setattr(ops.time, "time", lambda: 1767225600.0)

        runtime.observe(**OBSERVATION)

        assert (
            published(
                runtime.last_event,
                "lakehouse_last_event_timestamp_seconds",
                source="medallion",
            )
            == 1767225600.0
        )

    def test_failed_endpoint_startup_disables_metrics_and_observe_stays_silent(
        self, monkeypatch, capsys
    ) -> None:
        def boom(*args, **kwargs):
            raise OSError("address already in use")

        monkeypatch.setattr(prometheus_client, "start_http_server", boom)

        runtime = ops._RuntimeMetrics("9099")

        assert runtime.enabled is False
        assert "Prometheus metrics endpoint unavailable" in capsys.readouterr().err
        assert runtime.observe(**OBSERVATION) is None
        # Nothing was published, so no scrape can report a half-initialised app.
        assert runtime.events.collect()[0].samples == []

    def test_record_publishes_runtime_metrics_even_when_the_postgres_sink_is_off(
        self, served, monkeypatch
    ) -> None:
        monkeypatch.setattr(ops, "PROMETHEUS_METRICS_PORT", "9099")
        metrics = ops.Metrics()
        metrics.enabled = False

        metrics.record(**OBSERVATION)

        assert metrics.conn is None
        assert (
            published(
                metrics.runtime.processed,
                "lakehouse_processed",
                source="medallion",
                kind="rows",
            )
            == 7
        )
