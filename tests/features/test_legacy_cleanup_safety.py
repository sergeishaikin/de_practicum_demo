"""pytest-bdd steps for the legacy outbox cleanup safety contract.

Steps bind to the production callables: ``classify_manifests`` and
``cleanup_set_digest`` for the eligibility rules, and ``_pre_delete_gate`` for
the approval gate that guards the destructive step. All of them are pure, so the
feature stays T1 — no stack, default fast suite.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then, when

from iceberg.medallion.legacy_outbox_reconciliation import (
    SnapshotEvidence,
    classify_manifests,
    cleanup_set_digest,
)
from scripts.cleanup_legacy_outbox import APPROVED_COUNT, _pre_delete_gate

scenarios("legacy_cleanup_safety.feature")

pytestmark = [pytest.mark.bdd]

LOAD_ID = "load-a"
ORDER_ID = "order-a"

# The migration boundary sits at 200; a batch observed before it is legacy work,
# a batch observed after it is live work.
BEFORE_MIGRATION_MS = 100
AFTER_MIGRATION_MS = 300
MIGRATION_BOUNDARY = SnapshotEvidence(
    "migration", 200, None, "legacy-singleton-business-version-v1"
)


def _row(order_id: str, version: int | None) -> dict:
    return {
        "order_id": order_id,
        "customer": "customer",
        "amount": 10.0,
        "country": "DE",
        "status": "paid",
        "event_time": "2026-01-01T12:00:00",
        "event_date": "2026-01-01",
        "business_version": version,
    }


def _manifest(load_id: str) -> dict:
    return {
        "load_id": load_id,
        "_object_path": f"bucket/outbox/{load_id}.json",
        "bronze_data_files": ["data/file.parquet"],
        "source_paths": [f"landing/{load_id}.parquet"],
    }


@pytest.fixture
def context() -> dict:
    return {
        "observed_at_ms": BEFORE_MIGRATION_MS,
        "progress": {"work": {}, "completed": {}},
        "authoritative": [_row(ORDER_ID, 1)],
        "silver": [_row(ORDER_ID, 1)],
        "approval": {
            "in_flight_blocked": 0,
            "blocked": 0,
            "safe_stale": APPROVED_COUNT,
            "cleanup_set_digest": "approved-digest-placeholder",
            "cleanup_set": [],
        },
    }


# --- Given -----------------------------------------------------------------


@given("a legacy batch whose rows are represented in authoritative state")
def reconciled_batch(context: dict) -> None:
    context["manifest"] = _manifest(LOAD_ID)


@given("a legacy batch whose rows are absent from authoritative state")
def unreconciled_batch(context: dict) -> None:
    context["manifest"] = _manifest(LOAD_ID)
    context["authoritative"] = []
    context["silver"] = []


@given("the batch is still being processed")
def batch_in_flight(context: dict) -> None:
    context["progress"] = {"work": {LOAD_ID: {"status": "in_flight"}}, "completed": {}}


@given("the batch was created after the migration boundary")
def batch_after_boundary(context: dict) -> None:
    context["observed_at_ms"] = AFTER_MIGRATION_MS


@given("two proposed batches in one order")
def batches_one_order(context: dict) -> None:
    context["left"] = [
        {"load_id": "b", "manifest": "bucket/b.json"},
        {"load_id": "a", "manifest": "bucket/a.json"},
    ]


@given("the same two batches in the opposite order")
def batches_reversed(context: dict) -> None:
    context["right"] = list(reversed(context["left"]))


@given("a cleanup approval that matches the approved batch count")
def approval_with_expected_count(context: dict) -> None:
    context["approval"]["safe_stale"] = APPROVED_COUNT


@given("the approval reports a batch that is still being processed")
def approval_reports_in_flight(context: dict) -> None:
    context["approval"]["in_flight_blocked"] = 1


@given("the approval fingerprint does not match the recorded approval")
def approval_digest_mismatch(context: dict) -> None:
    context["approval"]["cleanup_set_digest"] = "not-the-approved-digest"


@given("the approval proposes a batch stored outside the outbox")
def approval_proposes_foreign_path(context: dict) -> None:
    # If the gate ever inspected batches before checking the fingerprint, this
    # path would raise "invalid manifest path" instead of the digest error.
    context["approval"]["cleanup_set"] = [
        {"load_id": LOAD_ID, "manifest": "somewhere-else/evil.json"}
    ]


# --- When ------------------------------------------------------------------


@when("the legacy batches are classified")
def classify(context: dict) -> None:
    manifest = context["manifest"]
    load_id = str(manifest["load_id"])
    context["result"] = classify_manifests(
        [manifest],
        {load_id: [_row(ORDER_ID, None)]},
        context["authoritative"],
        context["silver"],
        {
            load_id: [
                SnapshotEvidence(
                    snapshot_id=f"snapshot-{load_id}",
                    timestamp_ms=context["observed_at_ms"],
                    load_id=load_id,
                    migration_marker=None,
                )
            ]
        },
        MIGRATION_BOUNDARY,
        context["progress"],
    )


@when("both fingerprints are taken")
def take_fingerprints(context: dict) -> None:
    context["left_digest"] = cleanup_set_digest(context["left"])
    context["right_digest"] = cleanup_set_digest(context["right"])


@when("the cleanup gate runs")
def run_gate(context: dict) -> None:
    try:
        _pre_delete_gate(context["approval"], [])
        context["refusal"] = None
    except RuntimeError as exc:
        context["refusal"] = str(exc)


# --- Then ------------------------------------------------------------------


@then("the batch is eligible for cleanup")
def batch_eligible(context: dict) -> None:
    assert context["result"]["safe_stale"] == 1


@then("the batch is not eligible for cleanup")
def batch_not_eligible(context: dict) -> None:
    assert context["result"]["safe_stale"] == 0


@then("the proposed cleanup set contains exactly that batch")
def cleanup_set_holds_batch(context: dict) -> None:
    cleanup_set = context["result"]["cleanup_set"]
    assert [item["load_id"] for item in cleanup_set] == [LOAD_ID]


@then("the proposed cleanup set is empty")
def cleanup_set_empty(context: dict) -> None:
    # The safety property: an ineligible batch must never reach the set that
    # the destructive step consumes.
    assert context["result"]["cleanup_set"] == []


@then("the batch is withheld because it is still being processed")
def withheld_in_flight(context: dict) -> None:
    result = context["result"]
    assert result["in_flight_blocked"] == 1
    assert result["blocked_reasons"] == {"active_or_inflight_progress": 1}


@then("the batch is withheld as unsafe")
def withheld_unsafe(context: dict) -> None:
    result = context["result"]
    assert result["blocked"] == 1
    assert "order_id_missing_from_authoritative_bronze" in result["blocked_reasons"]


@then("the batch is reported as live work rather than withheld as unsafe")
def reported_as_live(context: dict) -> None:
    # Post-migration work is current, not stale: it is excluded from cleanup
    # without being reported as a safety failure.
    result = context["result"]
    assert result["live_post_migration"] == 1
    assert result["blocked"] == 0
    assert result["in_flight_blocked"] == 0
    assert result["blocked_reasons"] == {}


@then("the two fingerprints are identical")
def fingerprints_match(context: dict) -> None:
    assert context["left_digest"] == context["right_digest"]


@then("cleanup is refused because a batch is still being processed")
def refused_in_flight(context: dict) -> None:
    assert context["refusal"] is not None, "the gate allowed cleanup"
    assert "IN_FLIGHT_BLOCKED" in context["refusal"]


@then("cleanup is refused because the fingerprint does not match")
def refused_digest(context: dict) -> None:
    assert context["refusal"] is not None, "the gate allowed cleanup"
    assert (
        "cleanup digest" in context["refusal"]
    ), f"expected a fingerprint refusal, got: {context['refusal']}"
