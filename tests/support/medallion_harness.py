"""Live-stack harness for the medallion's Gold cutover and rollback.

Extracted from ``tests/integration/test_m4_gold_cutover.py`` when the cutover
contract moved into ``tests/features/gold_cutover.feature``. Plain importable
helpers rather than fixtures, so integration tests and BDD step definitions
share one way of driving the real medallion against an isolated namespace.

Connection settings are reused from ``writer_harness`` rather than duplicated —
both harnesses talk to the same MinIO and Iceberg REST catalog. Requires only
those two: no Trino, no Airflow, no Postgres (metrics are disabled, so the
canonical ``marts`` schema is never touched). That last constraint also rules
out a Postgres-backed liveness signal: ``ci-m5-gates.yml`` starts only MinIO and
the REST catalog.

A deployment proves it ran by *announcing a completed cycle* on stdout — see
``CycleWatcher`` — not by leaving a new Gold snapshot behind. The two were
equivalent until GLD-01; only the announcement stays true afterwards.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime

from pyarrow.fs import S3FileSystem
from pyiceberg.catalog.rest import RestCatalog

from medallion import iceberg_medallion as m
from tests.support.writer_harness import (
    ACCESS_KEY,
    BUCKET,
    ICEBERG_CATALOG_URI,
    ICEBERG_WAREHOUSE,
    REPO_ROOT,
    S3_ENDPOINT,
    SECRET_KEY,
    catalog,
    fs,
)

__all__ = [
    "catalog",
    "fs",
    "isolated_lake",
    "append_work",
    "make_row",
    "CycleWatcher",
    "parse_cycle_marker",
    "run_deployment",
    "start_medallion",
    "silver_state",
    "logical_gold",
    "gold_snapshot_count",
    "wait_for_completed",
    "wait_for_gold_rows",
]

# The accepted rollout stages, as env fragments. `rollback` is deliberately
# absent: M4 defines rollback as changing the Gold source only, which returns a
# cutover deployment to `shadow`.
STAGES = {
    "shadow": {"GOLD_SOURCE": "legacy", "SHADOW_COMPARE": "1"},
    "cutover": {"GOLD_SOURCE": "persisted_silver", "SHADOW_COMPARE": "1"},
    # Not an accepted state; used only to prove the service refuses to start.
    "unvalidated_cutover": {"GOLD_SOURCE": "persisted_silver", "SHADOW_COMPARE": "0"},
}


def make_row(order_id: str, version: int, amount: float, event_day: date) -> dict:
    timestamp = datetime(event_day.year, event_day.month, event_day.day, 12)
    return {
        "order_id": order_id,
        "customer": f"{order_id}-v{version}",
        "amount": amount,
        "country": "US",
        "status": "paid",
        "event_time": timestamp,
        "kafka_timestamp": timestamp,
        "kafka_partition": 0,
        "kafka_offset": version,
        "event_date": event_day,
        "business_version": version,
    }


def append_work(
    table, load_id: str, rows: list[dict], filesystem: S3FileSystem, prefix: str
) -> None:
    """Append a Bronze batch and record the outbox entry B2 consumes."""

    before = {item["file_path"] for item in table.inspect.data_files().to_pylist()}
    table.append(m._rows_to_silver(rows), snapshot_properties={"load-id": load_id})
    after = {item["file_path"] for item in table.inspect.data_files().to_pylist()}
    record = {
        "version": 1,
        "load_id": load_id,
        "source_paths": [f"m4/{load_id}.parquet"],
        "bronze_data_files": sorted(after - before),
        "row_count": len(rows),
    }
    with filesystem.open_output_stream(f"{BUCKET}/{prefix}/{load_id}.json") as output:
        output.write(json.dumps(record).encode("utf-8"))


def start_medallion(
    namespace: str, outbox_prefix: str, progress_path: str, *, stage: str
) -> subprocess.Popen:
    """Start a medallion deployment in one rollout stage."""

    assert stage in STAGES, f"unknown stage {stage!r}"
    env = os.environ.copy()
    env.update(
        {
            "ICEBERG_CATALOG_URI": ICEBERG_CATALOG_URI,
            "ICEBERG_WAREHOUSE": ICEBERG_WAREHOUSE,
            "BRONZE_NAMESPACE": namespace,
            "BRONZE_TABLE": "bronze",
            "SILVER_NAMESPACE": namespace,
            "SILVER_TABLE": "silver",
            "GOLD_NAMESPACE": namespace,
            "GOLD_TABLE": "gold",
            "MINIO_BUCKET": BUCKET,
            "S3_ENDPOINT": S3_ENDPOINT,
            "AWS_ACCESS_KEY_ID": ACCESS_KEY,
            "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
            "SILVER_MODE": "b2",
            "BRONZE_OUTBOX_PREFIX": outbox_prefix,
            "MEDALLION_PROGRESS_PATH": progress_path,
            "MEDALLION_COMPLETION_LEDGER_PREFIX": f"{namespace}/completion-ledger",
            "MEDALLION_INTERVAL_SECONDS": "1",
            "METRICS_ENABLED": "0",
            **STAGES[stage],
        }
    )
    return subprocess.Popen(
        [sys.executable, "iceberg/medallion/iceberg_medallion.py"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_completed(
    filesystem: S3FileSystem, progress_path: str, load_id: str, timeout: int = 90
) -> None:
    deadline = time.time() + timeout
    object_path = f"{BUCKET}/{progress_path}"
    while time.time() < deadline:
        try:
            with filesystem.open_input_file(object_path) as source:
                progress = json.loads(source.read().decode("utf-8"))
            if load_id in progress.get("completed", {}):
                return
        except (FileNotFoundError, OSError):
            pass
        time.sleep(1)
    raise AssertionError(f"work {load_id} did not complete within {timeout}s")


def wait_for_gold_rows(
    cat: RestCatalog, namespace: str, expected_rows: int, timeout: int = 60
) -> None:
    deadline = time.time() + timeout
    identifier = f"{namespace}.gold"
    while time.time() < deadline:
        try:
            if cat.load_table(identifier).scan().to_arrow().num_rows == expected_rows:
                return
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError(f"{identifier} did not reach {expected_rows} rows")


def gold_snapshot_count(cat: RestCatalog, namespace: str) -> int:
    try:
        return len(cat.load_table(f"{namespace}.gold").metadata.snapshots)
    except Exception:
        return 0


MARKER_FIELDS = frozenset({"cycle_id", "gold", "shadow", "duration_ms"})


def parse_cycle_marker(line: str) -> dict | None:
    """Read one medallion stdout line as a cycle-complete marker, else ``None``.

    Total by design: a harness that raises on a stray log line fails the test
    that happens to be running rather than the thing that is actually wrong, so
    anything unrecognised is simply not a marker.

    The token must be the line's *first* field. A line that merely mentions
    ``cycle-complete`` — a diagnostic quoting one, for instance — is not a
    completed cycle and must not be able to make a test pass.
    """

    fields = line.split()
    if not fields or fields[0] != m.CYCLE_COMPLETE_MARKER:
        return None
    marker: dict = {}
    for field in fields[1:]:
        key, separator, value = field.partition("=")
        if not separator or not key or not value:
            return None
        marker[key] = value
    if set(marker) != MARKER_FIELDS:
        return None
    try:
        marker["duration_ms"] = int(marker["duration_ms"])
    except ValueError:
        return None
    return marker


class CycleWatcher:
    """Watch a running deployment for the cycles it announces.

    This is the liveness proof: a deployment did work when it says it completed
    a cycle, which stays true whether or not that cycle rewrote Gold. Waiting on
    a Gold row count instead — the obvious alternative — returns immediately
    whenever a previous stage already produced those rows, so the deployment
    would be stopped before it ran at all. That reasoning is still correct and
    is recorded here so it is not re-proposed.

    Both pipes are drained on daemon threads. ``start_medallion`` pipes stdout
    *and* stderr, and an unread pipe buffer eventually stalls the child; that
    hazard predates the marker and is fixed by reading, not by the marker.
    """

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._markers: queue.Queue = queue.Queue()
        self._captured: list[str] = []
        self._lock = threading.Lock()
        self._threads = [
            threading.Thread(target=self._drain, args=(stream, is_stdout), daemon=True)
            for stream, is_stdout in ((process.stdout, True), (process.stderr, False))
            if stream is not None
        ]
        for thread in self._threads:
            thread.start()

    def _drain(self, stream, is_stdout: bool) -> None:
        for line in stream:
            with self._lock:
                self._captured.append(line)
            if not is_stdout:
                continue
            marker = parse_cycle_marker(line)
            if marker is not None:
                self._markers.put(marker)

    def output(self) -> str:
        """Everything captured from both pipes so far."""

        with self._lock:
            return "".join(self._captured)

    def _exhausted(self) -> bool:
        """True once no further marker can arrive.

        The queue is checked last: a marker read between the caller's timeout
        and this check is still a completed cycle, not a dead deployment.
        """

        return (
            self._process.poll() is not None
            and not any(thread.is_alive() for thread in self._threads)
            and self._markers.empty()
        )

    def wait_for_cycle_complete(
        self,
        *,
        timeout: float = 90,
        gold: str | None = None,
        shadow: str | None = None,
    ) -> dict:
        """Return the first announced cycle matching `gold` / `shadow`.

        Markers that do not match are discarded, so a caller waiting for a
        specific decision is not satisfied by an earlier cycle that made a
        different one.
        """

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                marker = self._markers.get(timeout=min(remaining, 0.05))
            except queue.Empty:
                if self._exhausted():
                    break
                continue
            if gold is not None and marker["gold"] != gold:
                continue
            if shadow is not None and marker["shadow"] != shadow:
                continue
            return marker

        expected = ", ".join(
            f"{name}={value}"
            for name, value in (("gold", gold), ("shadow", shadow))
            if value is not None
        )
        exit_code = self._process.poll()
        raise AssertionError(
            "the deployment announced no completed cycle"
            + (f" with {expected}" if expected else "")
            + f" within {timeout}s"
            + ("" if exit_code is None else f"; it exited with {exit_code}")
            + f"; captured output:\n{self.output()}"
        )

    def close(self) -> None:
        """Stop watching. Call after the process has been asked to stop."""

        for thread in self._threads:
            thread.join(timeout=5)


def run_deployment(
    namespace: str,
    outbox_prefix: str,
    progress_path: str,
    *,
    stage: str,
    await_load_id: str | None = None,
    await_gold_rows: int | None = None,
) -> None:
    """Run one deployment in `stage` until it completes a cycle, then stop it.

    Every deployment waits for a cycle *this* deployment announced, which is the
    proof that it ran rather than inheriting the previous stage's output.
    """

    cat = catalog()
    process = start_medallion(namespace, outbox_prefix, progress_path, stage=stage)
    watcher = CycleWatcher(process)
    try:
        if await_load_id is not None:
            wait_for_completed(fs(), progress_path, await_load_id)
        watcher.wait_for_cycle_complete()
        if await_gold_rows is not None:
            wait_for_gold_rows(cat, namespace, await_gold_rows)
        assert process.poll() is None, "the deployment stopped before it was told to"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        finally:
            watcher.close()


def silver_state(cat: RestCatalog, namespace: str) -> tuple[int, list[tuple]]:
    """Snapshot count and logical rows — what must not change on a Gold switch."""

    silver = cat.load_table(f"{namespace}.silver")
    rows = sorted(
        (
            row["order_id"],
            row["business_version"],
            row["customer"],
            row["amount"],
            row["event_date"],
        )
        for row in silver.scan().to_arrow().to_pylist()
    )
    return len(silver.metadata.snapshots), rows


def logical_gold(cat: RestCatalog, namespace: str) -> list[tuple]:
    rows = cat.load_table(f"{namespace}.gold").scan().to_arrow().to_pylist()
    return sorted(
        (
            row["event_date"],
            row["country"],
            row["status"],
            row["orders_count"],
            row["total_amount"],
            row["avg_amount"],
            row["distinct_customers"],
        )
        for row in rows
    )


@contextmanager
def isolated_lake():
    """Yield a per-run namespace with an empty Bronze table, then clean up.

    Everything is unique per run, so the medallion running against the canonical
    lake is never touched.
    """

    run_id = uuid.uuid4().hex[:8]
    namespace = f"cutover_{run_id}"
    outbox_prefix = f"m4/{run_id}/outbox"
    progress_path = f"m4/{run_id}/progress.json"
    cat = catalog()
    cat.create_namespace_if_not_exists(namespace)
    cat.create_table(
        f"{namespace}.bronze",
        schema=m.SILVER_SCHEMA,
        partition_spec=m.SILVER_PARTITION_SPEC,
    )
    try:
        yield namespace, outbox_prefix, progress_path
    finally:
        for name in ("gold", "silver", "bronze"):
            try:
                cat.drop_table(f"{namespace}.{name}")
            except Exception:
                pass
        try:
            cat.drop_namespace(namespace)
        except Exception:
            pass
        try:
            fs().delete_dir(f"{BUCKET}/m4/{run_id}")
        except Exception:
            pass
