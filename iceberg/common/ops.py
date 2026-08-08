from __future__ import annotations

import os
import sys
import time
from typing import Any

import psycopg2

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") == "1"
PROMETHEUS_METRICS_PORT = os.getenv("PROMETHEUS_METRICS_PORT")

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "de-demo-postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "dwh")
POSTGRES_USER = os.getenv("POSTGRES_USER", "app")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "app")

METRICS_DDL = """
create table if not exists marts.lakehouse_metrics (
    metric_ts timestamptz not null default now(),
    source text not null,
    load_id text,
    status text not null,
    rows_processed bigint not null default 0,
    files_processed bigint not null default 0,
    bronze_rows bigint not null default 0,
    silver_rows bigint not null default 0,
    gold_rows bigint not null default 0,
    duplicates_removed bigint not null default 0,
    quality_violations bigint not null default 0,
    duration_ms bigint not null default 0,
    work_available bigint not null default 0,
    work_in_flight bigint not null default 0,
    work_completed bigint not null default 0,
    keys_processed bigint not null default 0,
    lower_versions_ignored bigint not null default 0,
    ff14_conflicts bigint not null default 0,
    shadow_comparisons bigint not null default 0,
    shadow_mismatches bigint not null default 0,
    silver_duration_ms bigint not null default 0,
    gold_duration_ms bigint not null default 0,
    files_planned bigint not null default 0,
    bytes_planned bigint not null default 0,
    files_removed bigint not null default 0,
    files_added bigint not null default 0,
    bytes_removed bigint not null default 0,
    bytes_added bigint not null default 0,
    snapshot_delta bigint not null default 0
);
alter table marts.lakehouse_metrics add column if not exists work_available bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists work_in_flight bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists work_completed bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists keys_processed bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists lower_versions_ignored bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists ff14_conflicts bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists shadow_comparisons bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists shadow_mismatches bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists silver_duration_ms bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists gold_duration_ms bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists files_planned bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists bytes_planned bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists files_removed bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists files_added bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists bytes_removed bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists bytes_added bigint not null default 0;
alter table marts.lakehouse_metrics add column if not exists snapshot_delta bigint not null default 0;
"""


def pg_conn_params() -> dict[str, Any]:
    return {
        "host": POSTGRES_HOST,
        "port": POSTGRES_PORT,
        "dbname": POSTGRES_DB,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
    }


class Metrics:
    def __init__(self) -> None:
        self.enabled = METRICS_ENABLED
        self.conn: Any = None
        self.schema_ready = False
        self.runtime = _RuntimeMetrics(PROMETHEUS_METRICS_PORT)

    def _connect(self) -> None:
        if self.conn is None or self.conn.closed != 0:
            self.conn = psycopg2.connect(**pg_conn_params())
            self.conn.autocommit = True
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self.schema_ready:
            return
        with self.conn.cursor() as cur:
            cur.execute(METRICS_DDL)
        self.schema_ready = True

    def record(
        self,
        *,
        source: str,
        status: str,
        load_id: str | None = None,
        rows_processed: int = 0,
        files_processed: int = 0,
        bronze_rows: int = 0,
        silver_rows: int = 0,
        gold_rows: int = 0,
        duplicates_removed: int = 0,
        quality_violations: int = 0,
        duration_ms: int = 0,
        work_available: int = 0,
        work_in_flight: int = 0,
        work_completed: int = 0,
        keys_processed: int = 0,
        lower_versions_ignored: int = 0,
        ff14_conflicts: int = 0,
        shadow_comparisons: int = 0,
        shadow_mismatches: int = 0,
        silver_duration_ms: int = 0,
        gold_duration_ms: int = 0,
        files_planned: int = 0,
        bytes_planned: int = 0,
        files_removed: int = 0,
        files_added: int = 0,
        bytes_removed: int = 0,
        bytes_added: int = 0,
        snapshot_delta: int = 0,
    ) -> None:
        self.runtime.observe(
            source=source,
            status=status,
            rows_processed=rows_processed,
            files_processed=files_processed,
            duration_ms=duration_ms,
            work_available=work_available,
            work_in_flight=work_in_flight,
            work_completed=work_completed,
            keys_processed=keys_processed,
            lower_versions_ignored=lower_versions_ignored,
            ff14_conflicts=ff14_conflicts,
            shadow_mismatches=shadow_mismatches,
            silver_duration_ms=silver_duration_ms,
            gold_duration_ms=gold_duration_ms,
            files_planned=files_planned,
            bytes_planned=bytes_planned,
            files_removed=files_removed,
            files_added=files_added,
            bytes_removed=bytes_removed,
            bytes_added=bytes_added,
        )
        if not self.enabled:
            return
        try:
            self._connect()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    insert into marts.lakehouse_metrics (
                        metric_ts, source, load_id, status,
                        rows_processed, files_processed,
                        bronze_rows, silver_rows, gold_rows,
                        duplicates_removed, quality_violations, duration_ms,
                        work_available, work_in_flight, work_completed,
                        keys_processed, lower_versions_ignored, ff14_conflicts,
                        shadow_comparisons, shadow_mismatches,
                        silver_duration_ms, gold_duration_ms,
                        files_planned, bytes_planned, files_removed, files_added,
                        bytes_removed, bytes_added, snapshot_delta
                    ) values (
                        now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        source,
                        load_id,
                        status,
                        rows_processed,
                        files_processed,
                        bronze_rows,
                        silver_rows,
                        gold_rows,
                        duplicates_removed,
                        quality_violations,
                        duration_ms,
                        work_available,
                        work_in_flight,
                        work_completed,
                        keys_processed,
                        lower_versions_ignored,
                        ff14_conflicts,
                        shadow_comparisons,
                        shadow_mismatches,
                        silver_duration_ms,
                        gold_duration_ms,
                        files_planned,
                        bytes_planned,
                        files_removed,
                        files_added,
                        bytes_removed,
                        bytes_added,
                        snapshot_delta,
                    ),
                )
        except Exception as exc:
            print(
                f"Metrics write failed ({source}): {exc}",
                file=sys.stderr,
                flush=True,
            )

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None


class _RuntimeMetrics:
    """Best-effort in-process Prometheus metrics for writer and medallion."""

    def __init__(self, port: str | None) -> None:
        self.enabled = bool(port)
        if not self.enabled:
            return
        try:
            from prometheus_client import Counter, Gauge, Histogram, start_http_server

            from prometheus_client import CollectorRegistry

            registry = CollectorRegistry()
            self.events = Counter(
                "lakehouse_events",
                "Completed application metric records",
                ["source", "status"],
                registry=registry,
            )
            self.duration = Histogram(
                "lakehouse_duration_seconds",
                "Application operation duration",
                ["source"],
                registry=registry,
            )
            self.work = Gauge(
                "lakehouse_work",
                "Latest work state reported by an application",
                ["source", "state"],
                registry=registry,
            )
            self.correctness = Counter(
                "lakehouse_correctness",
                "Correctness observations reported by an application",
                ["source", "kind"],
                registry=registry,
            )
            self.processed = Gauge(
                "lakehouse_processed",
                "Latest processing counts reported by an application",
                ["source", "kind"],
                registry=registry,
            )
            self.stage_duration = Gauge(
                "lakehouse_stage_duration_seconds",
                "Latest stage duration reported by an application",
                ["source", "stage"],
                registry=registry,
            )
            self.files = Gauge(
                "lakehouse_files",
                "Latest file counts reported by an application",
                ["source", "kind"],
                registry=registry,
            )
            self.bytes = Gauge(
                "lakehouse_bytes",
                "Latest byte counts reported by an application",
                ["source", "kind"],
                registry=registry,
            )
            self.up = Gauge(
                "lakehouse_up",
                "Whether the application metrics endpoint is alive",
                ["source"],
                registry=registry,
            )
            self.last_event = Gauge(
                "lakehouse_last_event_timestamp_seconds",
                "Timestamp of the latest application metric",
                ["source"],
                registry=registry,
            )
            start_http_server(int(port), addr="0.0.0.0", registry=registry)
        except Exception as exc:
            self.enabled = False
            print(f"Prometheus metrics endpoint unavailable: {exc}", file=sys.stderr)

    def observe(self, **values: int | str) -> None:
        if not self.enabled:
            return
        source = str(values["source"])
        status = str(values["status"])
        self.up.labels(source).set(1)
        self.last_event.labels(source).set(time.time())
        self.events.labels(source, status).inc()
        self.duration.labels(source).observe(int(values["duration_ms"]) / 1000)
        for state in ("available", "in_flight", "completed"):
            self.work.labels(source, state).set(int(values[f"work_{state}"]))
        for kind in ("rows", "files", "keys"):
            self.processed.labels(source, kind).set(int(values[f"{kind}_processed"]))
        for kind in (
            "lower_versions_ignored",
            "ff14_conflicts",
            "shadow_mismatches",
        ):
            self.correctness.labels(source, kind).inc(int(values[kind]))
        self.stage_duration.labels(source, "silver").set(
            int(values["silver_duration_ms"]) / 1000
        )
        self.stage_duration.labels(source, "gold").set(
            int(values["gold_duration_ms"]) / 1000
        )
        for kind in ("planned", "removed", "added"):
            self.files.labels(source, kind).set(int(values[f"files_{kind}"]))
        for kind in ("planned", "removed", "added"):
            self.bytes.labels(source, kind).set(int(values[f"bytes_{kind}"]))
