"""pytest-bdd steps for the writer crash-recovery contract.

This feature replaces ``tests/integration/test_crash_recovery.py``: it drives
the real writer process against a live MinIO + Iceberg REST catalog through the
shared harness in ``tests/support/writer_harness.py``, and keeps that file's
assertions at full strength.

T2 — needs live dependencies, runs under the `integration` marker.
"""

from __future__ import annotations

import json
import time

import pyarrow.parquet as pq
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.support import writer_harness as h

scenarios("writer_crash_recovery.feature")

pytestmark = [pytest.mark.bdd, pytest.mark.integration]

LANDING_FILE = "part-00000.parquet"
SETTLE_SECONDS = 8
CRASH_TIMEOUT = 90


@pytest.fixture
def lake(tmp_path):
    with h.isolated_lake(tmp_path) as value:
        yield value


@pytest.fixture
def context(lake) -> dict:
    namespace, table, landing, state_file = lake
    return {
        "namespace": namespace,
        "table": table,
        "landing": landing,
        "state_file": state_file,
        "fs": h.fs(),
    }


def _published(context: dict) -> tuple[int, int]:
    return h.snapshot_count_and_rows(
        context["namespace"], context["table"], h.catalog()
    )


def _run_writer(context: dict, crash_mode: str | None):
    return h.start_writer(
        context["namespace"],
        context["table"],
        context["landing"],
        context["state_file"],
        crash_mode,
    )


# --- Given -----------------------------------------------------------------


@given(parsers.parse("a committed landing batch of {rows:d} orders"))
def committed_batch(context: dict, rows: int) -> None:
    path = h.landing_path(context["landing"], LANDING_FILE)
    with context["fs"].open_output_stream(path) as out:
        pq.write_table(h.orders_table(rows), out)
    h.mark_spark_committed(context["fs"], context["landing"], LANDING_FILE)
    context["source_path"] = path
    context["expected_rows"] = rows


# --- When ------------------------------------------------------------------


@when("the writer crashes immediately after committing the batch")
def crash_after_commit(context: dict) -> None:
    proc = _run_writer(context, "after")
    assert proc.wait(timeout=CRASH_TIMEOUT) == h.CRASH_AFTER_COMMIT_EXIT


@when("the writer crashes immediately before committing the batch")
def crash_before_commit(context: dict) -> None:
    proc = _run_writer(context, "before")
    assert proc.wait(timeout=CRASH_TIMEOUT) == h.CRASH_BEFORE_COMMIT_EXIT


@when("the writer restarts and settles")
def restart_and_settle(context: dict) -> None:
    proc = _run_writer(context, None)
    time.sleep(SETTLE_SECONDS)
    proc.terminate()
    proc.wait(timeout=10)


@when("the writer restarts and publishes the pending batch")
def restart_and_publish(context: dict) -> None:
    proc = _run_writer(context, None)
    deadline = time.time() + CRASH_TIMEOUT
    try:
        while time.time() < deadline:
            try:
                count, _ = _published(context)
                if count >= 1:
                    break
            except Exception:
                pass
            time.sleep(2)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# --- Then ------------------------------------------------------------------


@then("the batch is published exactly once")
@then("the batch is still published exactly once")
def published_exactly_once(context: dict) -> None:
    count, rows = _published(context)
    assert count == 1, f"expected exactly one snapshot, got {count}"
    assert rows == context["expected_rows"]
    assert (
        h.snapshot_business_versions(
            context["namespace"], context["table"], h.catalog()
        )
        == [1] * context["expected_rows"]
    )


@then("no batch remains pending")
def nothing_pending(context: dict) -> None:
    state = json.loads(context["state_file"].read_text(encoding="utf-8"))
    assert state["pending"] == {}


@then("the source file is recorded as done")
def source_marked_done(context: dict) -> None:
    state = json.loads(context["state_file"].read_text(encoding="utf-8"))
    assert context["source_path"] in state["done"]


@then("exactly one outbox record exists")
def one_outbox_record(context: dict) -> None:
    files = h.outbox_files(context["fs"], context["landing"])
    assert len(files) == 1, f"expected exactly one outbox record, got {files}"
