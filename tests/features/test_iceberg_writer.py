"""pytest-bdd steps for the Iceberg writer publication contract.

Scope boundary, checked against DoD rule 10 before writing:

* eligibility, load identity and commit-evidence validity are specified here,
  because ``tests/test_writer.py`` proves them through ``FakeFS``/``FakeTable``
  and internal functions, while these scenarios assert what a live Iceberg
  table does or does not contain;
* duplicate prevention is *not* specified here — it is already owned by
  ``writer_crash_recovery.feature``;
* commit-conflict retry is *not* specified here — forcing a real
  ``CommitFailedException`` needs a test-only seam, so it stays a unit test
  (``tests/test_writer.py::TestMain::test_commit_conflict_retries_then_succeeds``).

T2 — needs live dependencies, runs under the `integration` marker.
"""

from __future__ import annotations

import time

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.support import writer_harness as h

scenarios("iceberg_writer.feature")

pytestmark = [pytest.mark.bdd, pytest.mark.integration]

LANDING_FILE = "part-00000.parquet"
SETTLE_SECONDS = 12


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


# --- Given -----------------------------------------------------------------


@given(parsers.parse("a committed landing batch of {rows:d} orders"))
def committed_batch(context: dict, rows: int) -> None:
    h.write_landing_file(context["fs"], context["landing"], LANDING_FILE, rows)
    h.mark_spark_committed(context["fs"], context["landing"], LANDING_FILE)
    context["expected_rows"] = rows


@given(parsers.parse("a landing file of {rows:d} orders that Spark has not committed"))
def uncommitted_file(context: dict, rows: int) -> None:
    # The Parquet data is present and readable; only the Spark commit log that
    # declares it complete is missing.
    h.write_landing_file(context["fs"], context["landing"], LANDING_FILE, rows)
    context["expected_rows"] = rows


@given(
    parsers.parse("a landing file of {rows:d} orders with unreadable commit evidence")
)
def corrupt_commit_evidence(context: dict, rows: int) -> None:
    h.write_landing_file(context["fs"], context["landing"], LANDING_FILE, rows)
    h.write_corrupt_commit_log(context["fs"], context["landing"])
    context["expected_rows"] = rows


# --- When ------------------------------------------------------------------


@when("the writer runs and settles")
def writer_runs(context: dict) -> None:
    proc = h.start_writer(
        context["namespace"],
        context["table"],
        context["landing"],
        context["state_file"],
        None,
    )
    time.sleep(SETTLE_SECONDS)
    # Without this, "nothing is published" would also pass when the writer died
    # on startup - the scenario would prove its own breakage, not the contract.
    still_running = proc.poll() is None
    proc.terminate()
    proc.wait(timeout=10)
    assert still_running, "the writer exited before it could publish anything"


# --- Then ------------------------------------------------------------------


@then("nothing is published")
def nothing_published(context: dict) -> None:
    cat = h.catalog()
    if not h.table_exists(context["namespace"], context["table"], cat):
        return
    # A table may exist from an earlier step; it must hold no data either way.
    count, rows = h.snapshot_count_and_rows(context["namespace"], context["table"], cat)
    assert count == 0, f"expected no published snapshot, got {count}"
    assert rows == 0


@then("the batch is published exactly once")
def published_exactly_once(context: dict) -> None:
    count, rows = h.snapshot_count_and_rows(
        context["namespace"], context["table"], h.catalog()
    )
    assert count == 1, f"expected exactly one snapshot, got {count}"
    assert rows == context["expected_rows"]


@then("the publication records exactly one load identity")
def one_load_identity(context: dict) -> None:
    load_ids = h.snapshot_load_ids(context["namespace"], context["table"], h.catalog())
    assert len(load_ids) == 1, f"expected one recorded load identity, got {load_ids}"
    assert load_ids[0], "the recorded load identity is empty"
