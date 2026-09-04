"""Executable fitness functions for the `development-workflow` capability.

These check the repository-visible rules of the standing contract: standing CI
definitions must not name working branches, and each acceptance capability must
exist as one composable definition that is invocable without opening a pull
request.

Two of the rules are known to be violated when the contract is written. They are
recorded as strict xfails rather than as a red suite, so that the rule is
encoded now and the marker itself fails once Milestone 2 satisfies it — a strict
xfail that starts passing is an error, which forces the marker to be removed
rather than left behind as a stale exemption.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"

# `main` is the sole permanent integration branch, so naming it in a trigger
# cannot rot. Every other branch name is a working branch by definition.
PERMANENT_BRANCHES = frozenset({"main"})


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _triggers(doc: dict[str, Any]) -> dict[str, Any]:
    """Return the workflow's trigger mapping.

    YAML 1.1 resolves the bare key ``on`` to the boolean ``True``, so the
    mapping has to be looked up under both spellings.
    """

    raw = doc.get("on", doc.get(True))
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {event: None for event in raw}
    if isinstance(raw, str):
        return {raw: None}
    return {}


def _branch_names(triggers: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for config in triggers.values():
        if not isinstance(config, dict):
            continue
        for key in ("branches", "branches-ignore"):
            for value in config.get(key) or []:
                names.add(str(value))
    return names


def _workflows() -> dict[str, dict[str, Any]]:
    return {path.name: _load(path) for path in sorted(WORKFLOWS.glob("*.y*ml"))}


def _capability_workflows() -> dict[str, dict[str, Any]]:
    """Workflows that carry an acceptance capability.

    Derived rather than listed: a capability gate is one that verifies a
    proposed integration for a bounded set of paths and can also be invoked on
    demand. Deriving the set means a new capability workflow is covered by
    these rules without anyone remembering to add it here.
    """

    selected: dict[str, dict[str, Any]] = {}
    for name, doc in _workflows().items():
        triggers = _triggers(doc)
        pull_request = triggers.get("pull_request")
        if "workflow_dispatch" not in triggers:
            continue
        if isinstance(pull_request, dict) and pull_request.get("paths"):
            selected[name] = doc
    return selected


def _working_branch_references() -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for name, doc in _workflows().items():
        working = _branch_names(_triggers(doc)) - PERMANENT_BRANCHES
        if working:
            offenders[name] = working
    return offenders


@pytest.mark.architecture
def test_workflow_trigger_parsing_survives_the_yaml_on_keyword() -> None:
    """The detector is worthless if `on:` silently parses as a boolean key."""

    triggers = _triggers(_load(WORKFLOWS / "ci-pr.yml"))
    assert triggers, "workflow triggers did not parse"
    assert "pull_request" in triggers
    assert _branch_names(triggers) == {"main"}


@pytest.mark.architecture
def test_capability_workflows_are_discovered() -> None:
    """Guard against the capability rules passing because the set is empty."""

    capabilities = _capability_workflows()
    assert len(capabilities) >= 5
    assert "ci-ng05-tempo.yml" in capabilities
    assert "ci-ng06-loki.yml" in capabilities


@pytest.mark.architecture
def test_working_branch_detector_reports_the_known_violations() -> None:
    """Prove the detector detects, so the strict xfail below is not vacuous.

    This asserts the violation set observed on 2026-09-04 by equality. It fails
    if a new branch-pinned workflow appears, and it fails once the known two are
    converted — at which point it is replaced by the requirement it guards.
    """

    assert _working_branch_references() == {
        "ci-ng05-tempo.yml": {"feature/ng-0.5-tempo"},
        "ci-ng06-loki.yml": {"feature/ng-0.6-loki"},
    }


@pytest.mark.architecture
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Milestone 2 converts ci-ng05-tempo.yml and ci-ng06-loki.yml to "
        "workflow_call and removes their branch-pinned push triggers"
    ),
)
def test_standing_ci_does_not_name_working_branches() -> None:
    assert _working_branch_references() == {}


@pytest.mark.architecture
@pytest.mark.xfail(
    strict=True,
    reason="Milestone 2 makes each acceptance capability composable",
)
def test_capability_workflows_declare_workflow_call() -> None:
    missing = sorted(
        name
        for name, doc in _capability_workflows().items()
        if "workflow_call" not in _triggers(doc)
    )
    assert missing == []


@pytest.mark.architecture
def test_capability_workflows_retain_workflow_dispatch() -> None:
    """The exact-SHA escape hatch is what makes a validation-only PR avoidable.

    This already holds, and it is asserted so that Milestone 2's conversion to
    `workflow_call` cannot quietly drop it.
    """

    missing = sorted(
        name
        for name, doc in _capability_workflows().items()
        if "workflow_dispatch" not in _triggers(doc)
    )
    assert missing == []


@pytest.mark.architecture
def test_no_workflow_triggers_on_a_non_main_push() -> None:
    """A `push` trigger names an integration line, so only `main` may appear."""

    offenders = {}
    for name, doc in _workflows().items():
        push = _triggers(doc).get("push")
        if not isinstance(push, dict):
            continue
        working = {str(b) for b in push.get("branches") or []} - PERMANENT_BRANCHES
        if working:
            offenders[name] = sorted(working)

    assert offenders == {
        "ci-ng05-tempo.yml": ["feature/ng-0.5-tempo"],
        "ci-ng06-loki.yml": ["feature/ng-0.6-loki"],
    }, "the branch-pinned push triggers changed; update the contract evidence"
