from __future__ import annotations

import pytest

from medallion.legacy_outbox_reconciliation import cleanup_set_digest
from scripts import cleanup_legacy_outbox as cleanup
from scripts.cleanup_legacy_outbox import OUTBOX_ROOT, _pre_delete_gate


def receipt(**overrides) -> dict:
    value = {
        "schema_version": 2,
        "b2_projection_valid": True,
        "b2_projection_error": None,
        "in_flight_blocked": 0,
        "blocked": 0,
        "safe_stale": 140,
        "cleanup_set_digest": "wrong",
        "cleanup_set": [],
    }
    value.update(overrides)
    return value


def approved(monkeypatch, count: int = 2) -> tuple[list[dict], list[dict]]:
    """Approve a small synthetic cleanup set and return it with its records."""

    cleanup_set = [
        {"load_id": f"load-{index}", "manifest": f"{OUTBOX_ROOT}load-{index}.json"}
        for index in range(count)
    ]
    records = [
        {"load_id": item["load_id"], "_object_path": item["manifest"]}
        for item in cleanup_set
    ]
    monkeypatch.setattr(cleanup, "APPROVED_COUNT", count)
    monkeypatch.setattr(cleanup, "APPROVED_DIGEST", cleanup_set_digest(cleanup_set))
    return cleanup_set, records


def test_cleanup_gate_rejects_digest_mismatch_before_file_lookup() -> None:
    with pytest.raises(RuntimeError, match="cleanup digest"):
        _pre_delete_gate(receipt(), [])


def test_cleanup_gate_rejects_inflight_work() -> None:
    with pytest.raises(RuntimeError, match="IN_FLIGHT_BLOCKED"):
        _pre_delete_gate(receipt(in_flight_blocked=1), [])


def test_unprovable_projection_is_reported_instead_of_its_derived_failures(
    monkeypatch,
) -> None:
    """The withdrawal state must not read as a stale approval.

    An unprovable projection empties the cleanup set and turns every SAFE_STALE
    into BLOCKED, so both the BLOCKED gate and the digest gate would fire on a
    consequence rather than the cause.
    """

    cleanup_set, records = approved(monkeypatch)
    withdrawn = receipt(
        b2_projection_valid=False,
        b2_projection_error=(
            "Bronze contains rows without business_version; historical "
            "migration must complete before B2 reconciliation can be proven"
        ),
        blocked=len(cleanup_set),
        safe_stale=0,
        cleanup_set=[],
        cleanup_set_digest=cleanup_set_digest([]),
    )

    with pytest.raises(RuntimeError) as failure:
        _pre_delete_gate(withdrawn, records)

    message = str(failure.value)
    assert "the B2 projection is not provable" in message
    assert "without business_version" in message
    assert "BLOCKED is non-zero" not in message
    assert "cleanup digest" not in message


def test_stale_approval_still_fails_on_the_digest_when_the_projection_holds(
    monkeypatch,
) -> None:
    _cleanup_set, records = approved(monkeypatch)

    with pytest.raises(RuntimeError, match="cleanup digest"):
        _pre_delete_gate(receipt(safe_stale=2, cleanup_set_digest="0" * 64), records)


def test_gate_selects_the_approved_records_when_projection_and_digest_agree(
    monkeypatch,
) -> None:
    cleanup_set, records = approved(monkeypatch)

    selected = _pre_delete_gate(
        receipt(
            safe_stale=len(cleanup_set),
            cleanup_set=cleanup_set,
            cleanup_set_digest=cleanup_set_digest(cleanup_set),
        ),
        records,
    )

    assert selected == records


@pytest.mark.parametrize("schema", [None, 1, 3, "2"])
def test_unrecognised_receipt_schema_fails_closed(monkeypatch, schema) -> None:
    cleanup_set, records = approved(monkeypatch)
    evidence = receipt(
        safe_stale=len(cleanup_set),
        cleanup_set=cleanup_set,
        cleanup_set_digest=cleanup_set_digest(cleanup_set),
    )
    if schema is None:
        del evidence["schema_version"]
    else:
        evidence["schema_version"] = schema

    # An otherwise perfectly approvable receipt is still refused, so an older
    # format can never be read with permissive defaults.
    with pytest.raises(RuntimeError, match="unsupported legacy-outbox receipt schema"):
        _pre_delete_gate(evidence, records)
