from __future__ import annotations

import pytest

from scripts.cleanup_legacy_outbox import _pre_delete_gate


def receipt(**overrides) -> dict:
    value = {
        "in_flight_blocked": 0,
        "blocked": 0,
        "safe_stale": 140,
        "cleanup_set_digest": "wrong",
        "cleanup_set": [],
    }
    value.update(overrides)
    return value


def test_cleanup_gate_rejects_digest_mismatch_before_file_lookup() -> None:
    with pytest.raises(RuntimeError, match="cleanup digest"):
        _pre_delete_gate(receipt(), [])


def test_cleanup_gate_rejects_inflight_work() -> None:
    with pytest.raises(RuntimeError, match="IN_FLIGHT_BLOCKED"):
        _pre_delete_gate(receipt(in_flight_blocked=1), [])
