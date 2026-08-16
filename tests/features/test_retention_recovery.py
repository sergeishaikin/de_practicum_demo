"""pytest-bdd steps for the snapshot retention / writer recovery contract.

Steps bind to the production ``validate_retention_contract``. The numeric
parsing variants stay in ``tests/test_residual_remediation.py`` — the feature
states only the system guarantee.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from dags.recovery_contract import validate_retention_contract

scenarios("retention_recovery.feature")

pytestmark = [pytest.mark.bdd]


@pytest.fixture
def context() -> dict:
    return {}


# --- Given -----------------------------------------------------------------


@given(parsers.parse("a recovery horizon of {horizon}"))
def recovery_horizon(context: dict, horizon: str) -> None:
    context["horizon"] = horizon


@given(parsers.parse("a safety margin of {margin}"))
def safety_margin(context: dict, margin: str) -> None:
    context["margin"] = margin


# --- When ------------------------------------------------------------------


@when(parsers.parse("snapshot retention is set to {retention}"))
def evaluate(context: dict, retention: str) -> None:
    try:
        context["contract"] = validate_retention_contract(
            retention, context["horizon"], context["margin"]
        )
        context["error"] = None
    except ValueError as exc:
        context["contract"] = None
        context["error"] = str(exc)


# --- Then ------------------------------------------------------------------


@then("the retention contract is accepted")
def contract_accepted(context: dict) -> None:
    assert context["error"] is None, f"unexpectedly rejected: {context['error']}"
    contract = context["contract"]
    assert (
        contract.retention_seconds
        > contract.recovery_horizon_seconds + contract.safety_margin_seconds
    )


@then("the retention contract is rejected as unsafe for recovery")
def contract_rejected_unsafe(context: dict) -> None:
    assert context["contract"] is None, "an unsafe retention period was accepted"
    # The refusal must be the recovery-evidence rule, not a parsing failure.
    assert "retention contract violated" in context["error"], context["error"]


@then("the configuration is rejected")
def configuration_rejected(context: dict) -> None:
    assert context["contract"] is None, "an uninterpretable retention was accepted"
    assert context["error"] is not None
