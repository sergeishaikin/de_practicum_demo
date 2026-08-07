from __future__ import annotations

import os
import sys
from typing import Any

import psycopg2

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") == "1"

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
    duration_ms bigint not null default 0
);
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
    ) -> None:
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
                        duplicates_removed, quality_violations, duration_ms
                    ) values (now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
