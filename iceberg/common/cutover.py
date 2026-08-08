"""Executable M5 cutover gate.

The evaluator is deliberately pure: CI, an operator, or a deployment job can
provide the same evidence bundle and receive the same decision without
connecting to a particular metrics backend.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIRED_RUNTIME_CONFIG = {
    "SILVER_MODE": "b2",
    "GOLD_SOURCE": "persisted_silver",
    "SHADOW_COMPARE": "1",
}

# These are the only rollout states that the running medallion is allowed to
# start with.  In particular, persisted Silver must not become the Gold source
# while shadow validation is disabled.
RUNTIME_ROLLOUT_MATRIX = {
    ("legacy", "legacy", "0"): "legacy",
    ("b2", "legacy", "0"): "rollback",
    ("b2", "legacy", "1"): "shadow",
    ("b2", "persisted_silver", "1"): "cutover",
}


def _normalise_runtime_config(config: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(config.get("SILVER_MODE", "")).strip().lower(),
        str(config.get("GOLD_SOURCE", "")).strip().lower(),
        str(config.get("SHADOW_COMPARE", "")).strip().lower(),
    )


def validate_runtime_config(config: Mapping[str, Any]) -> dict[str, str]:
    """Reject rollout combinations that bypass the M5 shadow gate."""

    silver_mode, gold_source, shadow_compare = _normalise_runtime_config(config)
    key = (silver_mode, gold_source, shadow_compare)
    rollout = RUNTIME_ROLLOUT_MATRIX.get(key)
    if rollout is None:
        raise ValueError(
            "Unsafe medallion rollout configuration: "
            f"SILVER_MODE={silver_mode!r}, GOLD_SOURCE={gold_source!r}, "
            f"SHADOW_COMPARE={shadow_compare!r}"
        )
    return {
        "SILVER_MODE": silver_mode,
        "GOLD_SOURCE": gold_source,
        "SHADOW_COMPARE": shadow_compare,
        "rollout": rollout,
    }


def evaluate_cutover_gate(
    config: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    """Return an auditable pass/fail result for the M5 production cutover."""

    checks = {
        "runtime_config": all(
            str(config.get(name, "")).lower() == expected
            for name, expected in REQUIRED_RUNTIME_CONFIG.items()
        ),
        "shadow_comparison_success": evidence.get("shadow_comparison_success") is True,
        "unresolved_progress_zero": evidence.get("unresolved_progress", 1) == 0,
        "ff14_conflicts_zero": evidence.get("ff14_conflicts", 1) == 0,
        "recent_recovery_tests_passed": evidence.get("recent_recovery_tests_passed") is True,
        "gold_equivalence": evidence.get("gold_equivalence") is True,
        "rollback_verified": evidence.get("rollback_verified") is True,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "passed": not failed_checks,
        "checks": checks,
        "failed_checks": failed_checks,
        "required_runtime_config": dict(REQUIRED_RUNTIME_CONFIG),
    }
