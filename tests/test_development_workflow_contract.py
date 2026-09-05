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

import re
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


# --------------------------------------------------------------------------
# Documentation propagation
#
# The CI rules above check that the contract is enforced. These check that it
# is *discoverable*: the contract was adopted into `openspec/specs/` while the
# contributor guide still said no branch convention existed and neither
# instruction file mentioned branching at all, so an agent could obey OpenSpec
# authorisation and verification and still branch a new change off a legacy
# integration baseline. Enforcement in CI does not help before the first
# commit; only the documents an author reads do.
# --------------------------------------------------------------------------

CANONICAL_SPEC = "openspec/specs/development-workflow/spec.md"

# Documents that must carry the contract, and why each one.
PROPAGATION_TARGETS = {
    "AGENTS.md": "authoritative repository instruction file",
    "CLAUDE.md": "agent operating instructions",
    "docs/DEVELOPMENT.md": "contributor-facing development guide",
}

# The two rules that decide branch topology before any work happens. Matched
# against normalised text so markdown emphasis and code spans do not decide
# whether a policy is considered stated.
REQUIRED_CLAIMS = {
    "branches originate from current main": "from the current main",
    "pull requests target main": "target main",
}

# Claims that were true before the contract was adopted and are false after.
STALE_CLAIMS = (
    "no explicit convention is documented",
    "no pull-request template or review workflow is defined",
    "no convention exists",
)


def _normalise(raw: str) -> str:
    """Strip markdown emphasis and code spans, then flatten whitespace.

    Without this the rules would be asserting a particular way of writing the
    policy rather than the policy, and reflowing a paragraph would fail a gate.
    """

    stripped = raw.replace("*", "").replace("`", "").replace("**", "")
    return " ".join(stripped.split()).lower()


def _propagation_failures(root: Path = ROOT) -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}
    for relative in PROPAGATION_TARGETS:
        path = root / relative
        if not path.exists():
            failures[relative] = ["missing"]
            continue
        body = _normalise(path.read_text(encoding="utf-8"))
        problems = []
        if CANONICAL_SPEC not in body:
            problems.append(f"does not cite {CANONICAL_SPEC}")
        for label, phrase in REQUIRED_CLAIMS.items():
            if phrase not in body:
                problems.append(f"does not state that {label}")
        for stale in STALE_CLAIMS:
            if stale in body:
                problems.append(f"still claims: {stale!r}")
        if problems:
            failures[relative] = problems
    return failures


@pytest.mark.architecture
def test_the_canonical_spec_is_where_every_document_points() -> None:
    """A dangling pointer is worse than no pointer: it looks answered."""

    spec = ROOT / CANONICAL_SPEC
    assert spec.exists(), f"{CANONICAL_SPEC} does not exist"
    body = spec.read_text(encoding="utf-8")
    assert "## Recorded exceptions" in body, (
        "three documents send readers to the Recorded exceptions table; "
        "it must exist in the spec"
    )


@pytest.mark.architecture
def test_the_integration_contract_reached_the_documents_authors_read() -> None:
    assert _propagation_failures() == {}


@pytest.mark.architecture
def test_agents_md_lists_development_workflow_as_a_standing_capability() -> None:
    """The policy specs are read together; naming two of three hides the third.

    `AGENTS.md` enumerated `engineering-governance` and `verification-contract`
    and stopped there, which described authorisation and verification as the
    whole of the process contract.
    """

    body = _normalise((ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    for capability in (
        "engineering-governance",
        "development-workflow",
        "verification-contract",
    ):
        assert capability in body, f"AGENTS.md does not name {capability}"


@pytest.mark.architecture
def test_propagation_detector_reports_a_synthetic_violation(
    tmp_path: Path,
) -> None:
    """Prove the rules above are not passing because the detector went blind."""

    (tmp_path / "docs").mkdir(parents=True)
    compliant = (
        f"See {CANONICAL_SPEC}. Branch from the current `main`; "
        "pull requests target `main`."
    )
    (tmp_path / "AGENTS.md").write_text(compliant, encoding="utf-8")
    # Cites the spec and targets `main`, but omits where branches originate.
    (tmp_path / "CLAUDE.md").write_text(
        f"See {CANONICAL_SPEC}. Pull requests target `main`.",
        encoding="utf-8",
    )
    # States both rules but carries the pre-contract claim as well.
    (tmp_path / "docs/DEVELOPMENT.md").write_text(
        compliant + " No explicit convention is documented.",
        encoding="utf-8",
    )

    failures = _propagation_failures(tmp_path)
    assert "AGENTS.md" not in failures
    assert failures["CLAUDE.md"] == [
        "does not state that branches originate from current main"
    ]
    assert failures["docs/DEVELOPMENT.md"] == [
        "still claims: 'no explicit convention is documented'"
    ]


def test_propagation_detector_reports_a_missing_document(tmp_path: Path) -> None:
    """A deleted or renamed target must fail loudly rather than vacuously pass."""

    failures = _propagation_failures(tmp_path)
    assert set(failures) == set(PROPAGATION_TARGETS)
    assert all(problems == ["missing"] for problems in failures.values())


# --------------------------------------------------------------------------
# Evidence shape
#
# A `pull_request` run verifies the merge of head into *base*. When the base is
# not the integration target, the run is evidence about a merge that will never
# happen — which is how a green receipt came to be cited as NG-0.6 adoption
# evidence while its base was a legacy branch fifteen commits behind `main`.
#
# This rule was deferred by `standardize-trunk-based-development` because the
# only non-conforming file was the one the rule was written for, and it was
# frozen. Writing the checker then would have meant exempting it, which encodes
# the defect as permitted. NG-0.6 has since integrated (PR #14) and every
# citation has been re-anchored, so the rule lands with no exemption list.
# --------------------------------------------------------------------------

EVIDENCE_GLOB = "openspec/changes/**/evidence.md"

_RUN_ID = re.compile(r"\b\d{8,}\b")

# `pull_request` in an event-label position. Prose that merely discusses the
# trigger — "the `pull_request` paths filter is evaluated against the whole
# diff" — names no run and must not be read as a citation.
_PR_EVENT = re.compile(
    r"events?\s*[:=]?\s*pull_request|pull_request\s+events?\b|pull_request\s+run\b",
    re.I,
)

# Canonical inline form: `base main@978863de`.
_BASE_INLINE = re.compile(r"base\s*[:=]?\s*([A-Za-z][\w./-]*)@([0-9a-f]{7,40})", re.I)

# Tabulated form: a "Base branch" row and a "Base SHA" row in the same section.
_BASE_BRANCH_ROW = re.compile(r"base\s+branch\s*\|\s*([A-Za-z][\w./-]*)", re.I)
_BASE_SHA_ROW = re.compile(r"base\s+sha\s*\|\s*([0-9a-f]{7,40})", re.I)


def _normalise_markdown(raw: str) -> str:
    return raw.replace("`", "").replace("*", "")


def _sections(text: str) -> list[tuple[str, str]]:
    """Split a markdown document into (heading, body) sections.

    The section is the unit because that is how this repository writes
    evidence: a heading introduces one receipt, and the base may legitimately
    be stated in a summary table above the run table rather than repeated in
    every row.
    """

    sections: list[tuple[str, str]] = []
    heading, buf = "(preamble)", []
    for line in text.splitlines():
        if line.startswith("#"):
            sections.append((heading, "\n".join(buf)))
            heading, buf = line.lstrip("# ").strip(), []
        else:
            buf.append(line)
    sections.append((heading, "\n".join(buf)))
    return sections


def _cites_a_pull_request_run(body: str) -> bool:
    for line in body.splitlines():
        if (
            line.strip().startswith("|")
            and "pull_request" in line
            and _RUN_ID.search(line)
        ):
            return True
    return bool(_PR_EVENT.search(body) and _RUN_ID.search(body))


def _records_its_base(body: str) -> bool:
    if _BASE_INLINE.search(body):
        return True
    return bool(_BASE_BRANCH_ROW.search(body) and _BASE_SHA_ROW.search(body))


def _evidence_sections(root: Path) -> list[tuple[str, str, str]]:
    found = []
    for path in sorted(root.glob(EVIDENCE_GLOB)):
        rel = path.relative_to(root).as_posix()
        text = _normalise_markdown(path.read_text(encoding="utf-8"))
        found.extend((rel, heading, body) for heading, body in _sections(text))
    return found


def _evidence_shape_failures(root: Path = ROOT) -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}
    for rel, heading, body in _evidence_sections(root):
        if _cites_a_pull_request_run(body) and not _records_its_base(body):
            failures.setdefault(rel, []).append(heading)
    return failures


@pytest.mark.architecture
def test_evidence_citing_a_pull_request_run_records_its_base() -> None:
    assert _evidence_shape_failures() == {}


@pytest.mark.architecture
def test_evidence_shape_rule_has_citations_to_check() -> None:
    """Guard against the rule passing because it found nothing to inspect."""

    citing = [
        (rel, heading)
        for rel, heading, body in _evidence_sections(ROOT)
        if _cites_a_pull_request_run(body)
    ]
    assert len(citing) >= 5, f"detector found only {len(citing)} citations"


@pytest.mark.architecture
def test_evidence_shape_detector_reports_a_synthetic_violation() -> None:
    """Prove the rule is not passing because the detector went blind."""

    missing = _normalise_markdown(
        "Run `33901538965`, event `pull_request`, head `03416c6c`."
    )
    assert _cites_a_pull_request_run(missing)
    assert not _records_its_base(missing)

    assert _records_its_base(_normalise_markdown(missing + " Base `main@e697f305`."))

    tabulated = _normalise_markdown(
        "| Base branch | `main` |\n"
        "| Base SHA | `e697f30525ada` |\n"
        "\n"
        "| Workflow | Event | Run id |\n"
        "| --- | --- | --- |\n"
        "| CI | `pull_request` | `33901538965` |\n"
    )
    assert _cites_a_pull_request_run(tabulated)
    assert _records_its_base(tabulated)


@pytest.mark.architecture
def test_evidence_shape_detector_ignores_prose_about_the_trigger() -> None:
    """`pull_request` discussed as a concept is not a receipt.

    Without this the rule would demand a base SHA from a paragraph explaining
    how path filters are evaluated, and the only way to satisfy it would be to
    write a false one.
    """

    prose = (
        "ci-h1-clean.yml does not list its own path in the pull_request paths "
        "filter, but the workflow still runs on every push to this PR. The "
        "workflow_dispatch run started on that assumption (32193725758) was "
        "cancelled as a duplicate."
    )
    assert _RUN_ID.search(prose)
    assert "pull_request" in prose
    assert not _cites_a_pull_request_run(prose)
