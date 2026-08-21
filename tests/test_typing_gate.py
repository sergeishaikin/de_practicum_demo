"""The type-check gate earns its place only if it catches what Ruff misses.

NG-0.9's premise is that Ruff is a linter and not a type checker, so adding one
closes a real gap rather than duplicating a tool the repository already runs.
That premise is asserted here rather than assumed: the fixture below is a type
error and clean lint at the same time, and the test fails if either half stops
being true.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# A wrong return type. Ruff has no opinion about it; a type checker must.
TYPE_ERROR_RUFF_ACCEPTS = '''"""Fixture module - deliberately ill-typed, deliberately lint-clean."""

from __future__ import annotations


def row_count(rows: list[str]) -> int:
    """Annotated to return an int, returns a str."""
    return rows[0]
'''


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def ill_typed_module(tmp_path: Path) -> Path:
    module = tmp_path / "ill_typed_fixture.py"
    module.write_text(TYPE_ERROR_RUFF_ACCEPTS, encoding="utf-8")
    return module


def test_ruff_accepts_the_fixture(ill_typed_module: Path) -> None:
    """Half the proof: the fixture is not merely bad code that any tool rejects."""

    result = _run(["ruff", "check", str(ill_typed_module)], REPO_ROOT)

    assert result.returncode == 0, (
        "Ruff rejected the fixture, so it no longer demonstrates a gap Ruff "
        f"cannot see:\n{result.stdout}\n{result.stderr}"
    )


def test_mypy_rejects_the_fixture(ill_typed_module: Path) -> None:
    """The other half: the checker catches exactly what Ruff let through."""

    result = _run(["mypy", str(ill_typed_module)], REPO_ROOT)

    assert result.returncode != 0, (
        "mypy accepted a function that returns str from an int-annotated body; "
        f"the typing gate is not doing anything:\n{result.stdout}"
    )
    assert "return-value" in result.stdout, result.stdout


@pytest.mark.architecture
def test_the_typed_scope_is_declared_and_not_silently_narrowed() -> None:
    """Typed scope expands monotonically, so it has to be visible to a reader.

    Asserted on the committed configuration rather than by running the checker:
    the property is which modules are in scope, and a passing run says nothing
    about whether the scope was quietly reduced to make it pass.
    """

    config = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'files = ["iceberg"]' in config, "the typed scope must stay declared"
    assert "mypy==" in config, "the checker must be pinned, not floating"
    assert "warn_unused_ignores = true" in config, (
        "a suppression that stops being needed must become an error, or "
        "`type: ignore` outlives the problem it was added for"
    )
    assert "ignore_errors" not in config, (
        "ignore_errors silences a module wholesale; NG-0.9 requires narrow, "
        "coded suppressions with a reason instead"
    )


@pytest.mark.architecture
def test_third_party_suppressions_are_enumerated_not_blanket() -> None:
    """`ignore_missing_imports` is scoped to named packages that ship no py.typed.

    A global `ignore_missing_imports` would hide a genuinely missing first-party
    import as readily as an untyped third-party one.
    """

    config = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    override_section = config.split("[[tool.mypy.overrides]]", 1)

    assert len(override_section) == 2, "expected per-module overrides"
    body = override_section[1]
    assert "module = [" in body
    for package in ("pyarrow", "pyiceberg", "prometheus_client"):
        assert package in body, f"{package} ships no py.typed and must be named"
    assert (
        "psycopg2" not in body
    ), "psycopg2 has real stubs via types-psycopg2; it must not be suppressed"
