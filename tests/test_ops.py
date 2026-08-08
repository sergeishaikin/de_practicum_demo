from __future__ import annotations

from common import ops


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
        assert log[1][1][:11] == (
            "writer",
            "L1",
            "success",
            3,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        assert log[1][1][11:] == (0,) * 17
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
        assert log[1][1][11:21] == (2, 0, 4, 3, 1, 0, 1, 0, 11, 7)

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
