"""Structural checks for the OpenSpec backlog registers.

A backlog register is a markdown table that says what future work exists, what
gates it, what change it opens as, and whether it is authorised. Prose cannot
enforce any of that. This script can, so the register is a checkable artifact
rather than a drawing.

It checks, for every ``<backlog>/*/00-INDEX.md``:

* item ids are unique and well-formed;
* pre-assigned change ids are unique across the whole backlog, so the same work
  cannot start twice under two names;
* every declared dependency resolves to an item in the same register;
* the dependency graph is acyclic;
* row order is a valid execution order -- an item's dependencies all appear in
  earlier rows;
* **lifecycle state matches the repository**: an ``ACTIVE`` row has its change
  directory under ``openspec/changes/``, a ``DONE`` row has exactly one archive
  and no active directory, and a ``PLANNED`` row has neither;
* **a DONE archive is complete** -- proposal, design, tasks and evidence;
* **authorisation is traceable**: nothing is authorised without a named grant,
  nothing that has started is unauthorised, and a grant carries a date;
* **dependencies precede execution**: an item may not be ``ACTIVE`` or ``DONE``
  while a hard dependency is still ``PLANNED``;
* **the item file agrees with its row** -- the lifecycle header a file carries is
  the state the register records for it;
* any ordering document the register points at covers every item exactly once and
  never places an item before one of its hard dependencies.

The lifecycle checks exist because the register drifted from reality once
already: on 2026-08-20 three items had been authorised and two implemented while
every item file still declared itself ``PROPOSED`` with ``authorization NONE``,
and the old validator *required* that declaration -- enforcing an invariant that
had become false. A register that cannot represent completion will be believed
anyway, and a completed item read as a description of the present is how solved
work gets re-solved.

That last check exists because the register cannot catch it alone. A recommended
ordering published in a separate document — an ADR, say — can contradict the
dependency graph without either file being internally inconsistent, and on
2026-08-19 exactly that happened: ADR-0003 recommended ``NG-0.9`` first while the
register declared ``NG-0.1`` a hard dependency of it. Both documents validated.

Run it directly::

    uv run --locked python openspec/backlog/validate_backlog.py

Exit status is 0 when every register is structurally sound, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ITEM_ID = re.compile(r"^NG-\d+\.\d+$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_GATES = frozenset({"ADOPT", "EXPERIMENT"})
NO_DEPENDENCIES = "-"

# Where the work is. Deliberately small: every extra state is one more thing
# that can disagree with the repository.
VALID_STATES = frozenset({"PLANNED", "ACTIVE", "DONE", "STOPPED"})
STARTED_STATES = frozenset({"ACTIVE", "DONE", "STOPPED"})
SETTLED_STATES = frozenset({"DONE", "STOPPED"})

# What the work concluded. Separate from state, because a completed experiment
# that concludes DO_NOT_ADOPT succeeded.
VALID_DISPOSITIONS = frozenset({"pending", "ADOPTED", "DO_NOT_ADOPT"})

NO_AUTHORISATION = "none"
NO_DATE = "-"

# An archived change is named `<date>-<change-id>`, and must carry the full
# record rather than only the parts that were easy to write.
REQUIRED_ARCHIVE_FILES = ("proposal.md", "design.md", "tasks.md", "evidence.md")

# Each item file declares its own lifecycle, and it must match its row.
ITEM_LIFECYCLE = re.compile(r"^>\s*\*\*Lifecycle:\*\*\s*([A-Z]+)\s*$", re.MULTILINE)

# A register names its ordering document with this line; the ordering document
# marks each execution slot as a bare item id on a line of its own.
ORDERING_POINTER = re.compile(r"^Recommended ordering:\s*`([^`]+)`\s*$")
ORDERING_SLOT = re.compile(r"^\s*(NG-\d+\.\d+)\s*$")

# What every item file carries regardless of lifecycle. The freshness section is
# the one that must survive completion: a DONE item's premises are exactly the
# ones a later reader is most likely to take on trust.
REQUIRED_ITEM_MARKERS = ("## Freshness of external assumptions",)


@dataclass(frozen=True)
class Row:
    """One parsed register row."""

    item: str
    file: str
    gate: str
    depends_on: tuple[str, ...]
    change_id: str
    state: str
    disposition: str
    authorised_by: str
    authorised_at: str
    line_no: int


@dataclass
class Report:
    """Accumulated failures and the layering derived along the way."""

    errors: list[str] = field(default_factory=list)
    layers: dict[str, int] = field(default_factory=dict)

    def fail(self, register: Path, message: str) -> None:
        self.errors.append(f"{register}: {message}")


def _strip_cell(cell: str) -> str:
    return cell.strip().strip("`").strip()


def parse_register(register: Path) -> tuple[list[Row], list[str]]:
    """Parse the pipe table out of a register, returning rows and parse errors."""
    rows: list[Row] = []
    errors: list[str] = []
    in_table = False

    for line_no, raw in enumerate(register.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line.startswith("|"):
            in_table = False
            continue

        cells = [_strip_cell(c) for c in line.strip("|").split("|")]
        if cells and cells[0] == "Item":
            in_table = True
            continue
        if not in_table or set("".join(cells)) <= {"-", ":"}:
            continue

        if len(cells) != 9:
            errors.append(f"line {line_no}: expected 9 columns, found {len(cells)}")
            continue

        (
            item,
            file_name,
            gate,
            deps,
            change_id,
            state,
            disposition,
            authorised_by,
            authorised_at,
        ) = cells
        parsed_deps: tuple[str, ...] = ()
        if deps and deps != NO_DEPENDENCIES:
            parsed_deps = tuple(d.strip() for d in deps.split(",") if d.strip())

        rows.append(
            Row(
                item=item,
                file=file_name,
                gate=gate,
                depends_on=parsed_deps,
                change_id=change_id,
                state=state,
                disposition=disposition,
                authorised_by=authorised_by,
                authorised_at=authorised_at,
                line_no=line_no,
            )
        )

    if not rows:
        errors.append("no register rows found")
    return rows, errors


def check_identity(register: Path, rows: list[Row], report: Report) -> None:
    """Item ids well-formed and unique; gates drawn from the allowed set."""
    seen: set[str] = set()
    for row in rows:
        if not ITEM_ID.match(row.item):
            report.fail(register, f"line {row.line_no}: malformed item id {row.item!r}")
        if row.item in seen:
            report.fail(register, f"line {row.line_no}: duplicate item id {row.item!r}")
        seen.add(row.item)
        if row.gate not in VALID_GATES:
            report.fail(
                register,
                f"line {row.line_no}: gate {row.gate!r} is not one of "
                f"{sorted(VALID_GATES)}",
            )


def check_authorisation(register: Path, rows: list[Row], report: Report) -> None:
    """Authorisation is traceable to a named grant, and dated.

    A bare date records *when* but not *why*, which cannot distinguish a
    per-item operator grant from membership of a bounded programme. After the
    programme authorisation existed, that ambiguity became real.
    """
    for row in rows:
        authorised = row.authorised_by != NO_AUTHORISATION

        if authorised and not row.authorised_by:
            report.fail(
                register,
                f"line {row.line_no}: {row.item} has an empty authorisation grant",
            )
        if authorised and not ISO_DATE.match(row.authorised_at):
            report.fail(
                register,
                f"line {row.line_no}: {row.item} is authorised by "
                f"{row.authorised_by!r} but its date is {row.authorised_at!r}; "
                "expected an ISO date",
            )
        if not authorised and row.authorised_at != NO_DATE:
            report.fail(
                register,
                f"line {row.line_no}: {row.item} is unauthorised but carries the "
                f"date {row.authorised_at!r}",
            )
        if not authorised and row.state in STARTED_STATES:
            report.fail(
                register,
                f"line {row.line_no}: {row.item} is {row.state} with no "
                "authorisation grant; work may not start unauthorised",
            )


def check_lifecycle(register: Path, rows: list[Row], report: Report) -> None:
    """State and disposition are drawn from the allowed sets and agree."""
    for row in rows:
        if row.state not in VALID_STATES:
            report.fail(
                register,
                f"line {row.line_no}: {row.item} state {row.state!r} is not one of "
                f"{sorted(VALID_STATES)}",
            )
            continue
        if row.disposition not in VALID_DISPOSITIONS:
            report.fail(
                register,
                f"line {row.line_no}: {row.item} disposition {row.disposition!r} is "
                f"not one of {sorted(VALID_DISPOSITIONS)}",
            )
            continue

        if row.state == "DONE" and row.disposition == "pending":
            report.fail(
                register,
                f"line {row.line_no}: {row.item} is DONE with a pending "
                "disposition; a concluded item records what it concluded",
            )
        if row.state in {"PLANNED", "ACTIVE"} and row.disposition != "pending":
            report.fail(
                register,
                f"line {row.line_no}: {row.item} is {row.state} but already "
                f"records disposition {row.disposition!r}",
            )


def check_lifecycle_against_repository(
    register: Path, rows: list[Row], repo_root: Path, report: Report
) -> None:
    """The register's claims, checked against `changes/` and `changes/archive/`.

    This is the check the old validator could not make. A row saying `DONE` is
    a claim about the repository, and a claim nothing verifies is a drawing.
    """
    changes = repo_root / "openspec" / "changes"
    archive = changes / "archive"

    for row in rows:
        active = changes / row.change_id
        active_exists = active.is_dir()
        archived = (
            sorted(d for d in archive.glob(f"*-{row.change_id}") if d.is_dir())
            if archive.is_dir()
            else []
        )

        if row.state == "PLANNED":
            if active_exists:
                report.fail(
                    register,
                    f"{row.item} is PLANNED but {active.relative_to(repo_root)} "
                    "exists; implementation is already under way",
                )
            if archived:
                report.fail(
                    register,
                    f"{row.item} is PLANNED but an archive exists: "
                    f"{[d.name for d in archived]}",
                )

        elif row.state == "ACTIVE":
            if not active_exists:
                report.fail(
                    register,
                    f"{row.item} is ACTIVE but there is no "
                    f"{active.relative_to(repo_root)}",
                )
            if archived:
                report.fail(
                    register,
                    f"{row.item} is ACTIVE but its change is already archived as "
                    f"{[d.name for d in archived]}",
                )

        elif row.state == "DONE":
            if active_exists:
                report.fail(
                    register,
                    f"{row.item} is DONE but {active.relative_to(repo_root)} is "
                    "still an active change",
                )
            if len(archived) != 1:
                report.fail(
                    register,
                    f"{row.item} is DONE but has {len(archived)} archived changes "
                    f"matching {row.change_id!r}: {[d.name for d in archived]}",
                )
            else:
                missing = [
                    name
                    for name in REQUIRED_ARCHIVE_FILES
                    if not (archived[0] / name).is_file()
                ]
                if missing:
                    report.fail(
                        register,
                        f"{row.item}: archive {archived[0].name} is missing "
                        f"{missing}",
                    )

        elif row.state == "STOPPED" and active_exists:
            report.fail(
                register,
                f"{row.item} is STOPPED but {active.relative_to(repo_root)} is "
                "still present; a stopped item has no implementation in flight",
            )


def check_dependency_lifecycle(register: Path, rows: list[Row], report: Report) -> None:
    """Work does not start before its hard prerequisites conclude.

    Row order already keeps the *table* topological. This is the stronger claim:
    that execution respected the graph, not merely that the drawing did.
    """
    state = {row.item: row.state for row in rows}
    for row in rows:
        if row.state not in STARTED_STATES:
            continue
        for dep in row.depends_on:
            if state.get(dep) in SETTLED_STATES or dep not in state:
                continue
            report.fail(
                register,
                f"line {row.line_no}: {row.item} is {row.state} while its hard "
                f"dependency {dep} is {state[dep]}; a prerequisite must conclude "
                "first",
            )


def check_dependencies(register: Path, rows: list[Row], report: Report) -> None:
    """Dependencies resolve, the graph is acyclic, and row order is topological."""
    known = {row.item for row in rows}
    seen_so_far: set[str] = set()

    for row in rows:
        for dep in row.depends_on:
            if dep not in known:
                report.fail(
                    register,
                    f"line {row.line_no}: {row.item} depends on unknown item {dep!r}",
                )
            elif dep not in seen_so_far:
                report.fail(
                    register,
                    f"line {row.line_no}: {row.item} depends on {dep}, which appears "
                    "later in the register; row order is not a valid execution order",
                )
        seen_so_far.add(row.item)

    _check_acyclic(register, rows, known, report)


def _check_acyclic(
    register: Path, rows: list[Row], known: set[str], report: Report
) -> None:
    """Depth-first cycle detection, independent of row order."""
    graph = {row.item: [d for d in row.depends_on if d in known] for row in rows}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            cycle = " -> ".join(stack[stack.index(node) :] + [node])
            report.fail(register, f"dependency cycle: {cycle}")
            return
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, ()):
            visit(dep)
        stack.pop()
        state[node] = 2

    for item in graph:
        visit(item)


def compute_layers(rows: list[Row], report: Report) -> None:
    """Longest-path layering, recorded so the index drawing can be verified."""
    depth: dict[str, int] = {}

    def resolve(item: str, guard: frozenset[str]) -> int:
        if item in depth:
            return depth[item]
        if item in guard:
            return 0
        deps = next((r.depends_on for r in rows if r.item == item), ())
        value = 0 if not deps else 1 + max(resolve(d, guard | {item}) for d in deps)
        depth[item] = value
        return value

    for row in rows:
        resolve(row.item, frozenset())
    report.layers.update(depth)


def find_ordering_document(register: Path, repo_root: Path) -> Path | None:
    """Resolve the ordering document a register points at, if it names one."""
    for line in register.read_text(encoding="utf-8").splitlines():
        match = ORDERING_POINTER.match(line.strip())
        if match:
            return repo_root / match.group(1)
    return None


def parse_ordering(document: Path) -> list[str]:
    """Read execution slots, in order, from an ordering document.

    A slot is a bare item id alone on its line. Anything with surrounding prose
    is commentary - a paper gate, an annotation - and is deliberately not a slot,
    so the document can explain itself without confusing the check.
    """
    slots: list[str] = []
    for line in document.read_text(encoding="utf-8").splitlines():
        match = ORDERING_SLOT.match(line)
        if match:
            slots.append(match.group(1))
    return slots


def check_ordering(
    register: Path, rows: list[Row], repo_root: Path, report: Report
) -> None:
    """A published ordering may not place an item before a hard dependency."""
    document = find_ordering_document(register, repo_root)
    if document is None:
        return
    if not document.is_file():
        report.fail(register, f"ordering document not found: {document}")
        return

    slots = parse_ordering(document)
    position = {item: index for index, item in enumerate(slots)}
    known = {row.item for row in rows}
    label = document.name

    for item in slots:
        if item not in known:
            report.fail(register, f"{label}: orders unknown item {item!r}")

    if len(slots) != len(position):
        duplicates = sorted({i for i in slots if slots.count(i) > 1})
        report.fail(register, f"{label}: item(s) ordered more than once: {duplicates}")

    missing = sorted(known - set(slots))
    if missing:
        report.fail(register, f"{label}: item(s) never ordered: {missing}")

    for row in rows:
        if row.item not in position:
            continue
        for dep in row.depends_on:
            if dep not in position:
                continue
            if position[dep] >= position[row.item]:
                report.fail(
                    register,
                    f"{label}: orders {row.item} at slot {position[row.item]} but "
                    f"its hard dependency {dep} at slot {position[dep]}; an "
                    "ordering may not place an item before a dependency",
                )


def check_item_files(register: Path, rows: list[Row], report: Report) -> None:
    """Referenced files exist, carry a lifecycle header, and agree with the row.

    This deliberately no longer requires every file to declare itself
    ``PROPOSED`` with ``authorization NONE``. That invariant was true when the
    package was written and false the moment the first item shipped, and the
    check was enforcing it against completed work.

    What replaces it is stricter, not looser: the file must say which lifecycle
    state it is in, and it must be the same state the register records.
    """
    for row in rows:
        path = register.parent / row.file
        if not path.is_file():
            report.fail(register, f"line {row.line_no}: missing item file {row.file}")
            continue
        text = path.read_text(encoding="utf-8")

        for marker in REQUIRED_ITEM_MARKERS:
            if marker not in text:
                report.fail(register, f"{row.file}: missing required marker {marker!r}")

        match = ITEM_LIFECYCLE.search(text)
        if match is None:
            report.fail(
                register,
                f"{row.file}: no '**Lifecycle:**' header; every item declares the "
                "state it is in",
            )
            continue
        declared = match.group(1)
        if declared != row.state:
            report.fail(
                register,
                f"{row.file}: declares lifecycle {declared!r} but the register "
                f"records {row.state!r} for {row.item}",
            )

        # A completed item is read by people and agents looking for current
        # behaviour, and its body describes the platform *before* it landed.
        if row.state == "DONE" and "historical intent" not in text:
            report.fail(
                register,
                f"{row.file}: is DONE but does not warn that it is historical "
                "intent rather than current behaviour",
            )


def validate(backlog_root: Path, repo_root: Path | None = None) -> Report:
    """Validate every register under ``backlog_root``.

    ``repo_root`` anchors the ordering-document pointer, which a register writes
    as a repository-relative path. It defaults to the backlog's grandparent -
    ``<repo>/openspec/backlog`` - so the ordinary invocation needs no argument.
    """
    report = Report()
    if repo_root is None:
        repo_root = backlog_root.parent.parent
    registers = sorted(backlog_root.glob("*/00-INDEX.md"))
    if not registers:
        report.errors.append(f"{backlog_root}: no register found")
        return report

    change_ids: dict[str, str] = {}
    for register in registers:
        rows, parse_errors = parse_register(register)
        for message in parse_errors:
            report.fail(register, message)
        if not rows:
            continue

        check_identity(register, rows, report)
        check_lifecycle(register, rows, report)
        check_authorisation(register, rows, report)
        check_dependencies(register, rows, report)
        check_dependency_lifecycle(register, rows, report)
        check_lifecycle_against_repository(register, rows, repo_root, report)
        check_item_files(register, rows, report)
        check_ordering(register, rows, repo_root, report)
        compute_layers(rows, report)

        for row in rows:
            if row.change_id in change_ids:
                report.fail(
                    register,
                    f"line {row.line_no}: change id {row.change_id!r} is already "
                    f"assigned to {change_ids[row.change_id]}",
                )
            change_ids[row.change_id] = row.item

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--backlog-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="directory holding the backlog registers (default: this file's dir)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="anchor for ordering-document paths (default: the backlog's grandparent)",
    )
    args = parser.parse_args(argv)

    report = validate(args.backlog_root, args.repo_root)

    if report.errors:
        print(f"backlog validation FAILED ({len(report.errors)} problems)")
        for error in report.errors:
            print(f"  - {error}")
        return 1

    print(f"backlog validation OK ({len(report.layers)} items)")
    for layer in sorted(set(report.layers.values())):
        members = sorted(i for i, d in report.layers.items() if d == layer)
        print(f"  layer {layer}: {', '.join(members)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
