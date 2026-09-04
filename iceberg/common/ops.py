from __future__ import annotations

import os
import re
import sys
import time
from typing import Any

import psycopg2

from common.telemetry import current_trace_exemplar

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") == "1"
PROMETHEUS_METRICS_PORT = os.getenv("PROMETHEUS_METRICS_PORT")
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

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
    snapshot_delta bigint not null default 0,
    cycle_id text,
    phase text,
    bronze_snapshot_id bigint,
    silver_snapshot_id bigint,
    gold_snapshot_id bigint,
    shadow_skipped boolean not null default false,
    gold_skipped boolean not null default false
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
-- Phase 4 metric identity. cycle_id, phase and the three snapshot ids are
-- nullable with no default, deliberately: `cycle_id is null` is the predicate
-- that separates pre-Phase-4 rows from Phase-4 rows, and a `not null default ''`
-- would destroy it. Historical rows are never backfilled for the same reason --
-- an un-instrumented run must not be able to masquerade as an instrumented one.
alter table marts.lakehouse_metrics add column if not exists cycle_id text;
alter table marts.lakehouse_metrics add column if not exists phase text;
alter table marts.lakehouse_metrics add column if not exists bronze_snapshot_id bigint;
alter table marts.lakehouse_metrics add column if not exists silver_snapshot_id bigint;
alter table marts.lakehouse_metrics add column if not exists gold_snapshot_id bigint;
alter table marts.lakehouse_metrics add column if not exists shadow_skipped boolean not null default false;
alter table marts.lakehouse_metrics add column if not exists gold_skipped boolean not null default false;
"""

# The closed set of phase values a medallion cycle emits. `cycle` is the outer
# record and is always written last.
PHASES = ("b2", "shadow", "gold", "cycle")


def classify_metric_row(
    *,
    status: str,
    gold_duration_ms: int,
    cycle_id: str | None = None,
    phase: str | None = None,
) -> str:
    """Classify one `marts.lakehouse_metrics` row as an outer cycle or a nested phase.

    Phase-4 rows carry `cycle_id` and `phase` and need no inference: the row says
    what it is. Rows written before Phase 4 have `cycle_id IS NULL` and must be
    inferred, because `run_b2` and `_run_m4` both wrote `source="medallion"` and
    the outer `silver_duration_ms` already contained the nested B2 duration.

    The pre-era rule is deliberately **status-qualified**. The naive form --
    `gold_duration_ms = 0` means a nested B2 metric -- misclassifies
    `shadow_failed`, the safety-critical row, because `_run_m4` raises before Gold
    runs and therefore never sets that field. `shadow_failed` is an outer cycle
    that aborted, not a nested phase.

    Provenance of this rule, stated plainly: the `success` branches are grounded
    in recorded data, but the `shadow_failed` and `failed` branches were
    **derived by reading the emission sites in `iceberg_medallion.py`, not
    observed in recorded data**. Every one of the ten rows in
    `artifacts/b2-rollout/06-o1-window.json` has `status: success`.

    One caveat the classification compresses: a `failed` row may come from
    `run_b2` (a nested B2 phase) or from `_legacy_silver_cycle` under
    `QUALITY_FAIL_ON_VIOLATIONS=1` (an aborted legacy cycle). This function
    cannot tell which, and does not pretend to -- it returns `"nested"`, not
    `"b2"`. What makes the classification safe is the property both origins
    share: no outer record exists for that cycle.

    Returns one of `"cycle"`, `"b2"`, `"nested"` or `"unknown"`. A consumer
    wanting totals that do not double-count filters on `== "cycle"`, which is
    unaffected by the b2/nested distinction. Unrecognised input returns
    `"unknown"` rather than raising: this is a reporting helper over historical
    data, and a legacy status must not explode a query.
    """

    if cycle_id is not None:
        return phase if phase in PHASES else "unknown"
    if status == "shadow_failed":
        return "cycle"
    if status == "failed":
        return "nested"
    if status == "success":
        return "cycle" if gold_duration_ms else "b2"
    return "unknown"


def pg_conn_params() -> dict[str, Any]:
    return {
        "host": POSTGRES_HOST,
        "port": POSTGRES_PORT,
        "dbname": POSTGRES_DB,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
    }


def _bounded_trace_exemplar(exemplar: dict[str, str] | None) -> dict[str, str] | None:
    """Accept only the canonical, bounded trace-id exemplar shape."""

    if exemplar is None:
        return None
    if set(exemplar) != {"trace_id"} or not _TRACE_ID_RE.fullmatch(
        exemplar["trace_id"]
    ):
        print(
            "Prometheus exemplar rejected; recording metric without it",
            file=sys.stderr,
            flush=True,
        )
        return None
    return exemplar


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
        bronze_rows: int | None = 0,
        silver_rows: int = 0,
        gold_rows: int = 0,
        duplicates_removed: int | None = 0,
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
        cycle_id: str | None = None,
        phase: str | None = None,
        bronze_snapshot_id: int | None = None,
        silver_snapshot_id: int | None = None,
        gold_snapshot_id: int | None = None,
        shadow_skipped: bool = False,
        gold_skipped: bool = False,
    ) -> None:
        # Cycle-only observation. A nested phase record is durable in PostgreSQL
        # but must never reach a collector: the gauges are labelled by `source`
        # alone, so the outer record used to overwrite the nested record's values
        # with zeros seconds after they were measured -- resetting
        # lakehouse_files{kind="planned"}, lakehouse_bytes and
        # lakehouse_work{state="in_flight"}, and weakening LakehouseUnresolvedWork.
        # `phase is None` keeps the writer's call shape byte-for-byte unchanged.
        if phase in (None, "cycle"):
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
                        bytes_removed, bytes_added, snapshot_delta,
                        cycle_id, phase,
                        bronze_snapshot_id, silver_snapshot_id, gold_snapshot_id,
                        shadow_skipped, gold_skipped
                    ) values (
                        now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
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
                        cycle_id,
                        phase,
                        bronze_snapshot_id,
                        silver_snapshot_id,
                        gold_snapshot_id,
                        shadow_skipped,
                        gold_skipped,
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
        # Narrowed on `port` rather than on `self.enabled`: identical condition,
        # but it lets a type checker see that `port` is a `str` below.
        if not port:
            return
        try:
            from prometheus_client import Counter, Gauge, Histogram, start_http_server

            from prometheus_client import CollectorRegistry

            registry = CollectorRegistry()
            self.registry = registry
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
        duration = int(values["duration_ms"]) / 1000
        exemplar = _bounded_trace_exemplar(current_trace_exemplar())
        if exemplar is None:
            self.duration.labels(source).observe(duration)
        else:
            # Validate before Histogram mutates count/sum/buckets. Do not retry
            # after observe() raises: pinned clients may mutate before checking
            # exemplar metadata and a retry would double-count.
            self.duration.labels(source).observe(duration, exemplar=exemplar)
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
