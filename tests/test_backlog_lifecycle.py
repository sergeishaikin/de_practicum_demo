"""The programme register is checked against the repository, not trusted.

`validate_backlog.py` used to assert that every item file declared itself
`PROPOSED` with `authorization NONE`. That invariant was true when the package
was written and false the moment the first item shipped — and because it was
enforced, completed items had to keep claiming they were unauthorised future
work. A register that cannot represent completion gets believed anyway, and a
`DONE` item read as a description of the present is how solved work gets
re-solved.

These tests fix the replacement in place. Each negative case builds a small
register that lies in one specific way and asserts the checker catches it,
because a validator nobody has seen fail is a validator nobody knows works.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "openspec" / "backlog"))

import validate_backlog as vb  # noqa: E402

pytestmark = pytest.mark.architecture

HEADER = (
    "| Item | File | Gate | Depends on | Change | State | Disposition "
    "| Authorised by | At |\n|---|---|---|---|---|---|---|---|---|\n"
)

ITEM_BODY = {
    "PLANNED": (
        "> **Lifecycle:** PLANNED\n"
        "> **Execution authorization:** NONE\n\n"
        "## Freshness of external assumptions\n\nnothing yet.\n"
    ),
    "ACTIVE": (
        "> **Lifecycle:** ACTIVE\n\n"
        "## Freshness of external assumptions\n\nnothing yet.\n"
    ),
    "DONE": (
        "> **Lifecycle:** DONE\n"
        "> This document is historical intent, not current behaviour.\n\n"
        "## Freshness of external assumptions\n\nnothing yet.\n"
    ),
}


def build(
    tmp_path: Path, rows: list[dict], files: dict[str, str] | None = None
) -> Path:
    """A minimal backlog tree plus the `openspec/changes` layout it is checked
    against."""
    repo = tmp_path
    package = repo / "openspec" / "backlog" / "pkg"
    package.mkdir(parents=True)
    (repo / "openspec" / "changes" / "archive").mkdir(parents=True)

    lines = ["# Register\n\n", HEADER]
    for row in rows:
        lines.append(
            "| {item} | `{item}.md` | {gate} | {deps} | `{change}` | {state} "
            "| {disposition} | `{by}` | {at} |\n".format(**row)
        )
        declared = (files or {}).get(row["item"], row["state"])
        (package / f"{row['item']}.md").write_text(
            ITEM_BODY[declared], encoding="utf-8"
        )
    (package / "00-INDEX.md").write_text("".join(lines), encoding="utf-8")
    return repo


def row(
    item="NG-0.1",
    gate="ADOPT",
    deps="-",
    change="do-a-thing",
    state="PLANNED",
    disposition="pending",
    by="none",
    at="-",
):
    return dict(
        item=item,
        gate=gate,
        deps=deps,
        change=change,
        state=state,
        disposition=disposition,
        by=by,
        at=at,
    )


def errors(repo: Path) -> list[str]:
    return vb.validate(repo / "openspec" / "backlog", repo).errors


def make_active(repo: Path, change: str) -> None:
    (repo / "openspec" / "changes" / change).mkdir(parents=True, exist_ok=True)


def make_archive(repo: Path, change: str, *, complete: bool = True) -> None:
    directory = repo / "openspec" / "changes" / "archive" / f"2026-01-01-{change}"
    directory.mkdir(parents=True, exist_ok=True)
    names = vb.REQUIRED_ARCHIVE_FILES if complete else ("proposal.md",)
    for name in names:
        (directory / name).write_text("x", encoding="utf-8")


# --------------------------------------------------------------------------
# The baseline: a register that tells the truth
# --------------------------------------------------------------------------


def test_a_truthful_register_passes(tmp_path):
    """Proof the negative cases below mean something.

    Without this, every assertion that a lie is caught could be satisfied by a
    checker that rejects everything.
    """
    repo = build(
        tmp_path,
        [
            row(
                item="NG-0.1",
                state="DONE",
                disposition="ADOPTED",
                by="programme:p",
                at="2026-01-01",
                change="did-a-thing",
            ),
            row(
                item="NG-0.2",
                deps="NG-0.1",
                state="ACTIVE",
                by="programme:p",
                at="2026-01-02",
                change="doing-a-thing",
            ),
            row(item="NG-0.3", deps="NG-0.2", change="will-do-a-thing"),
        ],
    )
    make_archive(repo, "did-a-thing")
    make_active(repo, "doing-a-thing")

    assert errors(repo) == []


def test_the_real_register_is_consistent_with_the_repository():
    """The actual programme register, checked against the actual repository.

    This is the check that would have caught the drift in the first place, and
    it now runs in the fast suite rather than only when someone remembers to
    invoke the script.
    """
    report = vb.validate(REPO_ROOT / "openspec" / "backlog", REPO_ROOT)
    assert report.errors == [], "\n".join(report.errors)


# --------------------------------------------------------------------------
# The six ways a register can lie
# --------------------------------------------------------------------------


def test_done_without_an_archive_is_caught(tmp_path):
    repo = build(
        tmp_path,
        [row(state="DONE", disposition="ADOPTED", by="programme:p", at="2026-01-01")],
    )
    assert any("has 0 archived changes" in e for e in errors(repo)), errors(repo)


def test_done_with_an_incomplete_archive_is_caught(tmp_path):
    """An archive missing its evidence is not a completed change."""
    repo = build(
        tmp_path,
        [row(state="DONE", disposition="ADOPTED", by="programme:p", at="2026-01-01")],
    )
    make_archive(repo, "do-a-thing", complete=False)

    problems = errors(repo)
    assert any("is missing" in e and "evidence.md" in e for e in problems), problems


def test_active_without_an_active_change_is_caught(tmp_path):
    repo = build(tmp_path, [row(state="ACTIVE", by="programme:p", at="2026-01-01")])
    assert any("there is no" in e for e in errors(repo)), errors(repo)


def test_planned_with_implementation_already_underway_is_caught(tmp_path):
    """The register says nothing has started; the repository disagrees."""
    repo = build(tmp_path, [row(state="PLANNED")])
    make_active(repo, "do-a-thing")

    problems = errors(repo)
    assert any("implementation is already under way" in e for e in problems), problems


def test_a_dependent_item_may_not_run_before_its_prerequisite(tmp_path):
    """Row order keeps the drawing topological; this checks execution was."""
    repo = build(
        tmp_path,
        [
            row(item="NG-0.1", change="first-thing"),
            row(
                item="NG-0.2",
                deps="NG-0.1",
                change="second-thing",
                state="ACTIVE",
                by="programme:p",
                at="2026-01-02",
            ),
        ],
    )
    make_active(repo, "second-thing")

    problems = errors(repo)
    assert any("hard dependency NG-0.1 is PLANNED" in e for e in problems), problems


def test_an_item_file_disagreeing_with_its_row_is_caught(tmp_path):
    """Two places record the state; they must not diverge."""
    repo = build(
        tmp_path,
        [row(state="ACTIVE", by="programme:p", at="2026-01-01")],
        files={"NG-0.1": "PLANNED"},
    )
    make_active(repo, "do-a-thing")

    problems = errors(repo)
    assert any("declares lifecycle 'PLANNED'" in e for e in problems), problems


def test_authorisation_without_a_traceable_grant_is_caught(tmp_path):
    """A date alone says when, not why.

    After a bounded programme authorisation exists, "2026-08-20" cannot
    distinguish programme membership from a per-item operator grant.
    """
    repo = build(tmp_path, [row(state="ACTIVE", by="none", at="-")])
    make_active(repo, "do-a-thing")

    problems = errors(repo)
    assert any("no authorisation grant" in e for e in problems), problems


# --------------------------------------------------------------------------
# Supporting invariants
# --------------------------------------------------------------------------


def test_an_authorised_row_must_carry_a_date(tmp_path):
    repo = build(tmp_path, [row(state="ACTIVE", by="programme:p", at="-")])
    make_active(repo, "do-a-thing")
    assert any("expected an ISO date" in e for e in errors(repo)), errors(repo)


def test_an_unauthorised_row_may_not_carry_a_date(tmp_path):
    repo = build(tmp_path, [row(at="2026-01-01")])
    assert any("carries the date" in e for e in errors(repo)), errors(repo)


def test_a_done_item_must_record_what_it_concluded(tmp_path):
    repo = build(
        tmp_path,
        [row(state="DONE", disposition="pending", by="programme:p", at="2026-01-01")],
    )
    make_archive(repo, "do-a-thing")
    assert any("pending disposition" in e for e in errors(repo)), errors(repo)


def test_an_unfinished_item_may_not_record_an_outcome(tmp_path):
    repo = build(tmp_path, [row(state="PLANNED", disposition="ADOPTED")])
    assert any("already records disposition" in e for e in errors(repo)), errors(repo)


def test_a_completed_experiment_may_conclude_do_not_adopt(tmp_path):
    """State and disposition are separate for exactly this case.

    NG-1.3's own specification says its correct outcome may be
    `DO NOT IMPLEMENT`. That is a finished item, not a failed one.
    """
    repo = build(
        tmp_path,
        [
            row(
                gate="EXPERIMENT",
                state="DONE",
                disposition="DO_NOT_ADOPT",
                by="programme:p",
                at="2026-01-01",
            )
        ],
    )
    make_archive(repo, "do-a-thing")
    assert errors(repo) == []


def test_a_done_item_must_warn_that_it_is_historical(tmp_path):
    """The specific hazard: an agent reading a completed item as current state."""
    repo = build(
        tmp_path,
        [row(state="DONE", disposition="ADOPTED", by="programme:p", at="2026-01-01")],
    )
    make_archive(repo, "do-a-thing")
    package = repo / "openspec" / "backlog" / "pkg"
    (package / "NG-0.1.md").write_text(
        "> **Lifecycle:** DONE\n\n## Freshness of external assumptions\n\nx\n",
        encoding="utf-8",
    )

    problems = errors(repo)
    assert any("historical intent" in e for e in problems), problems


def test_every_completed_item_in_the_real_register_carries_the_warning():
    """Asserted against the live files, not only against fixtures."""
    package = REPO_ROOT / "openspec" / "backlog" / "next-generation"
    rows, parse_errors = vb.parse_register(package / "00-INDEX.md")
    assert not parse_errors, parse_errors

    done = [r for r in rows if r.state == "DONE"]
    assert done, "no completed items; this guard would pass vacuously"
    for item in done:
        text = (package / item.file).read_text(encoding="utf-8")
        assert "historical intent" in text, f"{item.file} lacks the warning"
        assert "**Lifecycle:** DONE" in text, f"{item.file} lacks its lifecycle header"
