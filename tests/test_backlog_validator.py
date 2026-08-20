"""The backlog validator's own tests, focused on the ordering check.

The other checks were negative-proven by mutating a scratch copy of the real
backlog when they were written. This one gets permanent tests because it is the
check that catches a defect the repository actually shipped: on 2026-08-19
ADR-0003 recommended running `NG-0.9` before `NG-0.1` while the register declared
`NG-0.1` a hard dependency of it. Neither document was internally inconsistent,
so nothing caught it.

Synthetic registers rather than the real one: a test that can only fail when
someone edits the live backlog would not describe the rule.

Lifecycle checks live in `tests/test_backlog_lifecycle.py`. The registers built
here are all `PLANNED`, because ordering is a property of the dependency graph
and not of how far execution has got.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "openspec" / "backlog" / "validate_backlog.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_backlog", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_backlog"] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator()

ITEM_TEMPLATE = """# {item}

> **Lifecycle:** PLANNED
> **Execution authorization:** NONE.

## Freshness of external assumptions

Planning assumptions, re-verified at promotion.
"""

REGISTER_HEADER = """# Synthetic register

Recommended ordering: `docs/ordering.md`

| Item | File | Gate | Depends on | Change | State | Disposition | Authorised by | At |
|---|---|---|---|---|---|---|---|---|
"""


def build_backlog(root: Path, rows: list[tuple[str, str, str]], ordering: str) -> Path:
    """Write a minimal backlog plus its ordering document.

    ``rows`` is (item, depends_on, change_id). Returns the backlog root, which is
    what ``validate`` is pointed at.
    """
    backlog_root = root / "openspec" / "backlog"
    register_dir = backlog_root / "synthetic"
    register_dir.mkdir(parents=True)

    lines = [REGISTER_HEADER]
    for item, deps, change_id in rows:
        file_name = f"{item}-item.md"
        (register_dir / file_name).write_text(
            ITEM_TEMPLATE.format(item=item), encoding="utf-8"
        )
        lines.append(
            f"| {item} | `{file_name}` | ADOPT | {deps} | `{change_id}` "
            "| PLANNED | pending | `none` | - |\n"
        )
    (register_dir / "00-INDEX.md").write_text("".join(lines), encoding="utf-8")

    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "ordering.md").write_text(ordering, encoding="utf-8")
    return backlog_root


def messages(report) -> str:
    return " | ".join(report.errors)


ORDER_OK = """# Ordering

```text
Wave 1:
  NG-0.1

Wave 2:
  NG-0.2
```
"""


def test_an_ordering_consistent_with_the_graph_passes(tmp_path):
    backlog = build_backlog(
        tmp_path,
        [("NG-0.1", "-", "add-one"), ("NG-0.2", "NG-0.1", "add-two")],
        ORDER_OK,
    )

    report = validator.validate(backlog, tmp_path)

    assert report.errors == []
    assert report.layers == {"NG-0.1": 0, "NG-0.2": 1}


def test_an_ordering_that_precedes_a_hard_dependency_fails(tmp_path):
    """The defect this check exists for: ADR-0003 versus the register, 2026-08-19."""

    inverted = """# Ordering

```text
Wave 1:
  NG-0.2

Wave 2:
  NG-0.1
```
"""
    backlog = build_backlog(
        tmp_path,
        [("NG-0.1", "-", "add-one"), ("NG-0.2", "NG-0.1", "add-two")],
        inverted,
    )

    report = validator.validate(backlog, tmp_path)

    assert report.errors, "an ordering that inverts a hard dependency must fail"
    assert "may not place an item before a dependency" in messages(report)
    assert "NG-0.2" in messages(report) and "NG-0.1" in messages(report)


def test_an_item_missing_from_the_ordering_fails(tmp_path):
    partial = """# Ordering

```text
Wave 1:
  NG-0.1
```
"""
    backlog = build_backlog(
        tmp_path,
        [("NG-0.1", "-", "add-one"), ("NG-0.2", "NG-0.1", "add-two")],
        partial,
    )

    report = validator.validate(backlog, tmp_path)

    assert "never ordered" in messages(report)
    assert "NG-0.2" in messages(report)


def test_an_item_ordered_twice_fails(tmp_path):
    duplicated = """# Ordering

```text
Wave 1:
  NG-0.1

Wave 2:
  NG-0.2
  NG-0.1
```
"""
    backlog = build_backlog(
        tmp_path,
        [("NG-0.1", "-", "add-one"), ("NG-0.2", "NG-0.1", "add-two")],
        duplicated,
    )

    report = validator.validate(backlog, tmp_path)

    assert "ordered more than once" in messages(report)


def test_prose_mentioning_an_item_is_not_an_execution_slot(tmp_path):
    """Ordering documents must be able to explain themselves.

    A paper gate names an item without scheduling it. Only a bare id alone on its
    line is a slot, so the commentary below must not make NG-0.2 look first.
    """

    with_commentary = """# Ordering

```text
Stage 0 - paper gate, not an execution slot:
  evaluate NG-0.2 before committing to it

Wave 1:
  NG-0.1

Wave 2:
  NG-0.2   this trailing note also stops it being a slot
  NG-0.2
```
"""
    backlog = build_backlog(
        tmp_path,
        [("NG-0.1", "-", "add-one"), ("NG-0.2", "NG-0.1", "add-two")],
        with_commentary,
    )

    report = validator.validate(backlog, tmp_path)

    assert report.errors == [], messages(report)


def test_a_register_naming_a_missing_ordering_document_fails(tmp_path):
    backlog = build_backlog(tmp_path, [("NG-0.1", "-", "add-one")], "placeholder")
    (tmp_path / "docs" / "ordering.md").unlink()

    report = validator.validate(backlog, tmp_path)

    assert "ordering document not found" in messages(report)


def test_a_register_without_an_ordering_pointer_skips_the_check(tmp_path):
    """A backlog with no recommended ordering is valid, not unchecked-and-failing."""

    backlog = build_backlog(tmp_path, [("NG-0.1", "-", "add-one")], "unused")
    register = backlog / "synthetic" / "00-INDEX.md"
    register.write_text(
        register.read_text(encoding="utf-8").replace(
            "Recommended ordering: `docs/ordering.md`\n", ""
        ),
        encoding="utf-8",
    )

    report = validator.validate(backlog, tmp_path)

    assert report.errors == []


@pytest.mark.architecture
def test_the_real_backlog_and_its_recommended_ordering_agree():
    """The live register against the live ADR, which is what actually regressed."""

    report = validator.validate(REPO_ROOT / "openspec" / "backlog", REPO_ROOT)

    assert report.errors == [], messages(report)
    assert report.layers["NG-0.9"] == 0, "NG-0.9 has no hard dependency"
    assert report.layers["NG-0.1"] == 0
