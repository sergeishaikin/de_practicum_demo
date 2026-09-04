"""Executable fitness functions for the `development-workflow` capability.

These check the repository-visible rules of the standing contract: standing CI
definitions must not name working branches, each acceptance capability must
exist as one composable definition that is invocable without opening a pull
request, and a required gate must trigger on edits to its own definition.

Every rule that asserts an absence is paired with a test that feeds the same
detector a synthetic violation, so a rule cannot pass because the detector
stopped working.
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


def _workflows(directory: Path = WORKFLOWS) -> dict[str, dict[str, Any]]:
    return {path.name: _load(path) for path in sorted(directory.glob("*.y*ml"))}


def _capability_workflows(directory: Path = WORKFLOWS) -> dict[str, dict[str, Any]]:
    """Workflows that carry an acceptance capability.

    Derived rather than listed: a capability gate is one that verifies a
    proposed integration for a bounded set of paths and can also be invoked on
    demand. Deriving the set means a new capability workflow is covered by
    these rules without anyone remembering to add it here.
    """

    selected: dict[str, dict[str, Any]] = {}
    for name, doc in _workflows(directory).items():
        triggers = _triggers(doc)
        pull_request = triggers.get("pull_request")
        if "workflow_dispatch" not in triggers:
            continue
        if isinstance(pull_request, dict) and pull_request.get("paths"):
            selected[name] = doc
    return selected


def _working_branch_references(directory: Path = WORKFLOWS) -> dict[str, set[str]]:
    offenders: dict[str, set[str]] = {}
    for name, doc in _workflows(directory).items():
        working = _branch_names(_triggers(doc)) - PERMANENT_BRANCHES
        if working:
            offenders[name] = working
    return offenders


def _write_workflow(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(body, encoding="utf-8")


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
def test_standing_ci_does_not_name_working_branches() -> None:
    assert _working_branch_references() == {}


@pytest.mark.architecture
def test_working_branch_detector_reports_a_synthetic_violation(
    tmp_path: Path,
) -> None:
    """Prove the rule above is not passing because the detector went blind."""

    _write_workflow(
        tmp_path,
        "ci-example.yml",
        "name: Example\non:\n  push:\n    branches: [feature/example]\n",
    )
    assert _working_branch_references(tmp_path) == {
        "ci-example.yml": {"feature/example"}
    }


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

    assert offenders == {}


@pytest.mark.architecture
def test_capability_push_triggers_are_filtered_to_permanent_branches() -> None:
    """An unfiltered `push` reintroduces branch gating without naming a branch.

    Verifying the integrated result on `main` is legitimate and expected — that
    is what `ci-s1-dbt.yml` does. What the rule forbids is a `push` trigger
    that fires on whatever branch the work happens to sit on, which is the
    branch-driven gating this capability removes, expressed without a branch
    name for the previous rule to catch.
    """

    offenders = {}
    for name, doc in _capability_workflows().items():
        push = _triggers(doc).get("push")
        if push is None and "push" not in _triggers(doc):
            continue
        branches = push.get("branches") if isinstance(push, dict) else None
        if not branches or not set(map(str, branches)) <= PERMANENT_BRANCHES:
            offenders[name] = branches
    assert offenders == {}


@pytest.mark.architecture
def test_capability_workflows_declare_workflow_call() -> None:
    missing = sorted(
        name
        for name, doc in _capability_workflows().items()
        if "workflow_call" not in _triggers(doc)
    )
    assert missing == []


@pytest.mark.architecture
def test_capability_workflows_retain_workflow_dispatch() -> None:
    """The exact-SHA escape hatch is what makes a validation-only PR avoidable."""

    missing = sorted(
        name
        for name, doc in _capability_workflows().items()
        if "workflow_dispatch" not in _triggers(doc)
    )
    assert missing == []


@pytest.mark.architecture
def test_capability_workflows_trigger_on_edits_to_themselves() -> None:
    """A required gate must not be editable without running.

    Without this, a pull request can change an acceptance gate's own logic and
    the gate stays silent, so the change that weakens the check is the one
    change the check never sees.
    """

    missing = []
    for name, doc in _capability_workflows().items():
        paths = _triggers(doc)["pull_request"].get("paths") or []
        if f".github/workflows/{name}" not in paths:
            missing.append(name)
    assert sorted(missing) == []


@pytest.mark.architecture
def test_self_reference_detector_reports_a_synthetic_violation(
    tmp_path: Path,
) -> None:
    """Prove the self-reference rule is not passing vacuously."""

    _write_workflow(
        tmp_path,
        "ci-example.yml",
        "name: Example\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "  pull_request:\n"
        '    paths: ["src/**"]\n',
    )
    capabilities = _capability_workflows(tmp_path)
    assert "ci-example.yml" in capabilities
    paths = _triggers(capabilities["ci-example.yml"])["pull_request"]["paths"]
    assert ".github/workflows/ci-example.yml" not in paths


DISPATCHER = "ci-capability-dispatch.yml"


def _local_reusable_targets(directory: Path = WORKFLOWS) -> dict[str, set[str]]:
    """Map each workflow to the local reusable workflows its jobs call."""

    calls: dict[str, set[str]] = {}
    for name, doc in _workflows(directory).items():
        targets = {
            str(job["uses"]).split("/")[-1]
            for job in (doc.get("jobs") or {}).values()
            if isinstance(job, dict) and str(job.get("uses", "")).startswith("./")
        }
        if targets:
            calls[name] = targets
    return calls


@pytest.mark.architecture
def test_dispatcher_is_not_a_capability_workflow() -> None:
    """Pin the classification instead of relying on it being incidental.

    The dispatcher owns invocation semantics, not verification. If it ever
    acquired a path-filtered `pull_request` trigger it would be classified as a
    capability gate, and the `workflow_call` and self-reference rules would
    start applying to a file they were never written for.
    """

    assert DISPATCHER not in _capability_workflows()
    assert (WORKFLOWS / DISPATCHER).exists()


@pytest.mark.architecture
def test_reusable_targets_exist_and_declare_workflow_call() -> None:
    """A `uses:` pointing at a missing or non-callable workflow fails at run time.

    Static resolution here means a renamed capability workflow breaks the unit
    test job on every pull request, rather than breaking a dispatch that
    somebody runs weeks later expecting a receipt.
    """

    broken: dict[str, list[str]] = {}
    for caller, targets in _local_reusable_targets().items():
        for target in sorted(targets):
            path = WORKFLOWS / target
            if not path.exists():
                broken.setdefault(caller, []).append(f"{target}: missing")
            elif "workflow_call" not in _triggers(_load(path)):
                broken.setdefault(caller, []).append(f"{target}: no workflow_call")
    assert broken == {}


@pytest.mark.architecture
def test_dispatcher_capability_options_map_to_called_workflows() -> None:
    """Every offered choice must actually dispatch something.

    Without this, renaming a job or an option leaves a selectable capability
    that silently runs nothing and still reports success.
    """

    doc = _load(WORKFLOWS / DISPATCHER)
    options = set(
        _triggers(doc)["workflow_dispatch"]["inputs"]["capability"]["options"]
    )
    jobs = doc["jobs"]
    for option in sorted(options):
        assert option in jobs, f"capability option '{option}' has no job"
        assert str(jobs[option].get("uses", "")).startswith(
            "./.github/workflows/"
        ), f"capability option '{option}' does not call a local workflow"
    assert options, "dispatcher offers no capabilities"


@pytest.mark.architecture
def test_dispatcher_requires_a_full_expected_sha() -> None:
    """Exact-SHA verification must name the SHA, not whatever a ref resolves to.

    `workflow_dispatch` runs against a ref. Without a required expected SHA the
    receipt says only "whatever that ref pointed at when someone clicked", which
    is precisely the ambiguity an exact-SHA receipt is supposed to remove.
    """

    inputs = _triggers(_load(WORKFLOWS / DISPATCHER))["workflow_dispatch"]["inputs"]
    assert inputs["expected_sha"]["required"] is True
    assert inputs["expected_sha"]["type"] == "string"

    preflight = _load(WORKFLOWS / DISPATCHER)["jobs"]["preflight"]
    body = yaml.safe_dump(preflight)
    assert "[0-9a-f]{40}" in body, "preflight does not check the SHA's shape"
    assert "github.sha" in body, "preflight does not compare against the resolved ref"
