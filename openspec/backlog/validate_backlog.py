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
* every item's ``Authorised`` cell reads ``no`` or an ISO date;
* every referenced item file exists and carries the headers that mark it as
  unauthorised future work.

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

REQUIRED_ITEM_MARKERS = (
    "**Status:** PROPOSED",
    "**Execution authorization:** NONE",
    "## Freshness of external assumptions",
)


@dataclass(frozen=True)
class Row:
    """One parsed register row."""

    item: str
    file: str
    gate: str
    depends_on: tuple[str, ...]
    change_id: str
    authorised: str
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

        if len(cells) != 6:
            errors.append(f"line {line_no}: expected 6 columns, found {len(cells)}")
            continue

        item, file_name, gate, deps, change_id, authorised = cells
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
                authorised=authorised,
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
    """Every item is unauthorised, or carries the ISO date it was authorised on."""
    for row in rows:
        if row.authorised == "no":
            continue
        if not ISO_DATE.match(row.authorised):
            report.fail(
                register,
                f"line {row.line_no}: {row.item} authorised cell is "
                f"{row.authorised!r}; expected 'no' or an ISO date",
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


def check_item_files(register: Path, rows: list[Row], report: Report) -> None:
    """Referenced files exist and still declare themselves unauthorised."""
    for row in rows:
        path = register.parent / row.file
        if not path.is_file():
            report.fail(register, f"line {row.line_no}: missing item file {row.file}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in REQUIRED_ITEM_MARKERS:
            if marker not in text:
                report.fail(register, f"{row.file}: missing required marker {marker!r}")


def validate(backlog_root: Path) -> Report:
    """Validate every register under ``backlog_root``."""
    report = Report()
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
        check_authorisation(register, rows, report)
        check_dependencies(register, rows, report)
        check_item_files(register, rows, report)
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
    args = parser.parse_args(argv)

    report = validate(args.backlog_root)

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
