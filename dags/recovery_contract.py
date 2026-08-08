"""Executable retention contract for writer recovery evidence.

The writer uses Bronze snapshot summaries as a recovery/idempotency signal.
Maintenance therefore must retain snapshots beyond the maximum period in which
a writer retry can need that signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_DURATION_RE = re.compile(r"^(?P<amount>\d+)(?P<unit>s|m|h|d)$", re.IGNORECASE)
_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}


@dataclass(frozen=True)
class RetentionRecoveryContract:
    retention: str
    recovery_horizon: str
    safety_margin: str
    retention_seconds: int
    recovery_horizon_seconds: int
    safety_margin_seconds: int


def _parse_duration(value: str, *, allow_zero: bool) -> int:
    """Convert the supported maintenance duration syntax to seconds."""

    match = _DURATION_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(
            f"invalid duration {value!r}; expected a positive integer followed "
            "by s, m, h, or d"
        )
    amount = int(match.group("amount"))
    if amount < 0 or (amount == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"duration must be {qualifier}, got {value!r}")
    return amount * _UNIT_SECONDS[match.group("unit").lower()]


def parse_duration(value: str) -> int:
    """Convert a positive maintenance duration to seconds."""

    return _parse_duration(value, allow_zero=False)


def validate_retention_contract(
    retention: str,
    recovery_horizon: str,
    safety_margin: str = "0s",
) -> RetentionRecoveryContract:
    """Validate that expiry is strictly beyond the recovery safety boundary."""

    retention_seconds = parse_duration(retention)
    recovery_horizon_seconds = parse_duration(recovery_horizon)
    safety_margin_seconds = _parse_duration(safety_margin, allow_zero=True)
    required_seconds = recovery_horizon_seconds + safety_margin_seconds
    if retention_seconds <= required_seconds:
        raise ValueError(
            "FF-10 retention contract violated: MAINTENANCE_RETENTION "
            f"({retention}) must be greater than "
            "MAINTENANCE_RECOVERY_HORIZON + "
            "MAINTENANCE_RECOVERY_SAFETY_MARGIN "
            f"({recovery_horizon} + {safety_margin}) because writer recovery "
            "uses Bronze snapshot summaries"
        )
    return RetentionRecoveryContract(
        retention=retention,
        recovery_horizon=recovery_horizon,
        safety_margin=safety_margin,
        retention_seconds=retention_seconds,
        recovery_horizon_seconds=recovery_horizon_seconds,
        safety_margin_seconds=safety_margin_seconds,
    )
