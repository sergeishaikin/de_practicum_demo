from __future__ import annotations

import os
import time

import psycopg2
from prometheus_client import Gauge, start_http_server

PORT = int(os.getenv("PROMETHEUS_METRICS_PORT", "9104"))
POLL_SECONDS = int(os.getenv("PROMETHEUS_EXPORTER_POLL_SECONDS", "15"))
PG_PARAMS = {
    "host": os.getenv("POSTGRES_HOST", "de-demo-postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "dwh"),
    "user": os.getenv("POSTGRES_USER", "app"),
    "password": os.getenv("POSTGRES_PASSWORD", "app"),
}

EXPORTER_UP = Gauge("lakehouse_exporter_up", "Whether the durable metrics exporter can query Postgres")
SOURCE_UP = Gauge("lakehouse_source_up", "Latest durable source status", ["source"])
SOURCE_LAST_EVENT = Gauge(
    "lakehouse_source_last_event_timestamp_seconds",
    "Timestamp of the latest durable source metric",
    ["source"],
)
SOURCE_DURATION = Gauge(
    "lakehouse_source_last_duration_seconds",
    "Latest durable source duration",
    ["source"],
)
MAINTENANCE_UP = Gauge(
    "lakehouse_maintenance_up",
    "Whether the latest maintenance audit is healthy",
)
MAINTENANCE_LAST_EVENT = Gauge(
    "lakehouse_maintenance_last_event_timestamp_seconds",
    "Timestamp of the latest maintenance audit",
)


def collect() -> None:
    with psycopg2.connect(**PG_PARAMS) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select distinct on (source)
                    source, status,
                    extract(epoch from metric_ts),
                    duration_ms
                from marts.lakehouse_metrics
                order by source, metric_ts desc
                """
            )
            source_rows = cursor.fetchall()
            for source, status, timestamp, duration_ms in source_rows:
                SOURCE_UP.labels(source).set(
                    1 if status in {"success", "ok", "noop"} else 0
                )
                SOURCE_LAST_EVENT.labels(source).set(float(timestamp))
                SOURCE_DURATION.labels(source).set(int(duration_ms) / 1000)

            cursor.execute(
                """
                select max(run_ts), bool_and(status in ('ok', 'noop'))
                from marts.maintenance_runs
                """
            )
            timestamp, healthy = cursor.fetchone()
            if timestamp is not None:
                MAINTENANCE_LAST_EVENT.set(timestamp.timestamp())
                MAINTENANCE_UP.set(1 if healthy else 0)
    EXPORTER_UP.set(1)


def main() -> None:
    start_http_server(PORT, addr="0.0.0.0")
    while True:
        try:
            collect()
        except Exception:
            EXPORTER_UP.set(0)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
