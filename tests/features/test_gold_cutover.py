"""pytest-bdd steps for the live Gold cutover and rollback contract.

Scope boundary, checked against DoD rule 10 before writing:

* what a shadow comparison *decides* — equality, mismatch classification,
  fail-closed ordering — is specified in ``shadow_cutover.feature`` against
  in-memory doubles and is deliberately not restated here;
* this feature adds only what the doubles cannot show: that each accepted stage
  survives a real deployment against a live catalog, that persisted Silver keeps
  the same Iceberg snapshots across a Gold-source switch and its rollback, and
  that an unaccepted stage never reaches a running service, because
  ``validate_runtime_config`` is called outside ``main()``'s retry loop and so
  terminates the process rather than being logged and retried.
* the shadow certification receipt gets one scenario here for the same reason:
  *what* a certificate decides is specified against in-memory doubles in
  ``tests/test_m4_gold.py``, but cross-restart durability is not observable
  there at all. A second, freshly started deployment reading a certificate a
  previous process left in a real object store, and declining to redo a
  comparison and a Gold rebuild because of it, needs a real catalog and a real
  process boundary or it proves nothing.

One rule the passing path cannot observe is recorded honestly rather than
faked: with validation enabled the two projections are required to agree, so a
*successful* run cannot reveal which one fed Gold. Proving that post-rollback
validation is still active needs deliberate divergence (fault injection), which
is a separate scenario and is not attempted here.

T2 — needs live MinIO + Iceberg REST catalog, runs under the `integration`
marker. Everything is per-run isolated; the canonical lake is never touched.
"""

from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, scenarios, then, when

from tests.support import medallion_harness as h

scenarios("gold_cutover.feature")

pytestmark = [pytest.mark.bdd, pytest.mark.integration]

DAY_ONE = date(2026, 1, 1)
DAY_TWO = date(2026, 1, 2)

SEED_LOAD = "001-seed"
UPDATE_LOAD = "002-update"

# Two batches: an opening pair, then a later version of "a" plus a stale
# observation of "b". Resolving them exercises a real B2 cycle rather than a
# pass-through, so the Silver the cutover inherits is genuinely derived.
SEED_ROWS = [("a", 1, 10.0, DAY_ONE), ("b", 1, 20.0, DAY_ONE)]
UPDATE_ROWS = [
    ("a", 3, 30.0, DAY_TWO),
    ("a", 5, 50.0, DAY_TWO),
    ("b", 0, 20.0, DAY_ONE),
]

EXPECTED_CURRENT_STATE = [
    ("a", 5, "a-v5", 50.0, DAY_TWO),
    ("b", 1, "b-v1", 20.0, DAY_ONE),
]


@pytest.fixture
def lake():
    with h.isolated_lake() as value:
        yield value


@pytest.fixture
def context(lake) -> dict:
    namespace, outbox_prefix, progress_path = lake
    return {
        "namespace": namespace,
        "outbox_prefix": outbox_prefix,
        "progress_path": progress_path,
        "catalog": h.catalog(),
    }


def _deploy(context: dict, stage: str, **kwargs) -> dict:
    return h.run_deployment(
        context["namespace"],
        context["outbox_prefix"],
        context["progress_path"],
        stage=stage,
        **kwargs,
    )


def _remember_state(context: dict) -> None:
    context["silver"] = h.silver_state(context["catalog"], context["namespace"])
    context["gold"] = h.logical_gold(context["catalog"], context["namespace"])


# --- Given -----------------------------------------------------------------


@given("a lake holding two batches of committed order observations")
def seeded_lake(context: dict) -> None:
    bronze = context["catalog"].load_table(f"{context['namespace']}.bronze")
    filesystem = h.fs()
    for load_id, rows in ((SEED_LOAD, SEED_ROWS), (UPDATE_LOAD, UPDATE_ROWS)):
        h.append_work(
            bronze,
            load_id,
            [h.make_row(*row) for row in rows],
            filesystem,
            context["outbox_prefix"],
        )


# --- When ------------------------------------------------------------------


@when("the deployment serves metrics from the full rebuild")
def deploy_shadow(context: dict) -> None:
    _deploy(context, "shadow", await_load_id=UPDATE_LOAD, await_gold_rows=2)


@when("the metrics source is switched to the incremental state")
def deploy_cutover(context: dict) -> None:
    _remember_state(context)
    _deploy(context, "cutover", await_gold_rows=2)


@when("the metrics source is rolled back to the full rebuild")
def deploy_after_rollback(context: dict) -> None:
    _remember_state(context)
    # Rollback changes the Gold source only, which returns the deployment to the
    # `shadow` stage it occupied before cutover.
    _deploy(context, "shadow", await_gold_rows=2)


@when("a second deployment serves metrics from the incremental state")
def deploy_certified_cutover(context: dict) -> None:
    _remember_state(context)
    context["gold_snapshots"] = h.gold_snapshot_count(
        context["catalog"], context["namespace"]
    )
    # The wait carries the assertion: this deployment has to *announce* a cycle
    # that skipped both, and nothing it inherited can satisfy that.
    context["cycle"] = _deploy(
        context,
        "cutover",
        require_gold="skipped",
        require_shadow="skipped",
        await_gold_rows=2,
    )


@when(
    "a deployment is started that serves metrics from the incremental state "
    "with validation disabled"
)
def deploy_unvalidated(context: dict) -> None:
    process = h.start_medallion(
        context["namespace"],
        context["outbox_prefix"],
        context["progress_path"],
        stage="unvalidated_cutover",
    )
    stdout, stderr = process.communicate(timeout=60)
    context["exit_code"] = process.returncode
    context["output"] = f"{stdout}\n{stderr}"


# --- Then ------------------------------------------------------------------


@then("the daily metrics are published")
def gold_published(context: dict) -> None:
    gold = h.logical_gold(context["catalog"], context["namespace"])
    assert gold, "the daily metrics table is empty"


@then("the incremental business state holds the current version of each order")
def silver_is_current_state(context: dict) -> None:
    _, rows = h.silver_state(context["catalog"], context["namespace"])
    assert rows == EXPECTED_CURRENT_STATE


@then("the daily metrics are unchanged")
def gold_unchanged(context: dict) -> None:
    assert h.logical_gold(context["catalog"], context["namespace"]) == context["gold"]


@then("the incremental business state is untouched")
def silver_untouched(context: dict) -> None:
    snapshots, rows = h.silver_state(context["catalog"], context["namespace"])
    before_snapshots, before_rows = context["silver"]
    # Snapshot identity, not just row equality: a rewrite that happened to
    # produce the same rows would still add a snapshot.
    assert snapshots == before_snapshots, "the Gold switch rewrote persisted Silver"
    assert rows == before_rows


@then("it announces a cycle that skipped both the comparison and the rebuild")
def cycle_skipped_the_redundant_work(context: dict) -> None:
    assert context["cycle"]["shadow"] == "skipped"
    assert context["cycle"]["gold"] == "skipped"


@then("the daily metrics table gained no snapshot")
def gold_snapshots_unchanged(context: dict) -> None:
    # Catalog-level proof of the Gold skip, independent of what the deployment
    # said about itself.
    assert (
        h.gold_snapshot_count(context["catalog"], context["namespace"])
        == context["gold_snapshots"]
    )


@then("the service exits instead of running")
def service_exited(context: dict) -> None:
    assert context["exit_code"] not in (
        0,
        None,
    ), "an unaccepted stage produced a running service"


@then("it reports the configuration as unsafe")
def reported_unsafe(context: dict) -> None:
    assert "Unsafe medallion rollout configuration" in context["output"]


@then("no daily metrics are published")
def no_gold(context: dict) -> None:
    with pytest.raises(Exception):
        context["catalog"].load_table(f"{context['namespace']}.gold")
