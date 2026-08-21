"""Contracts for the SQL mutation gate in scripts/mutation_test.py.

The catalogue integrity checks run in the fast suite: they need no database and
catch the failure mode that would otherwise silently hollow out the gate - a
mutation whose `find` pattern no longer matches the model, which would report as
an error rather than as coverage.

The harness self-test needs a live warehouse and is marked `integration`.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt" / "warehouse"

# A plain import, so the module is registered in sys.modules. Loading it via
# importlib.util.module_from_spec without registering breaks @dataclass, which
# resolves its own module from sys.modules at class-creation time.
sys.path.insert(0, str(ROOT / "scripts"))
import mutation_test  # noqa: E402


def test_every_mutation_pattern_still_matches_its_model() -> None:
    """A stale `find` pattern turns a mutation into an error, which would quietly
    reduce the gate's coverage while CI still looked green on the count."""

    assert mutation_test.CATALOGUE, "the mutation catalogue is empty"
    for mutation in [*mutation_test.CATALOGUE, mutation_test.SELF_TEST]:
        target = PROJECT / mutation.path
        assert target.is_file(), f"{mutation.name}: {mutation.path} does not exist"
        source = target.read_text(encoding="utf-8")
        occurrences = source.count(mutation.find)
        assert occurrences == 1, (
            f"{mutation.name}: pattern occurs {occurrences} times in "
            f"{mutation.path}; it must match exactly once"
        )
        assert mutation.find != mutation.into, f"{mutation.name}: mutation is a no-op"


def test_every_killer_names_a_real_unit_test() -> None:
    """The selector must resolve, or dbt reports 'nothing to do' and the mutation
    would be scored as an error instead of killing anything."""

    definitions = (PROJECT / "models" / "marts" / "unit_tests.yml").read_text(
        encoding="utf-8"
    )
    for mutation in [*mutation_test.CATALOGUE, mutation_test.SELF_TEST]:
        assert (
            f"- name: {mutation.killer}" in definitions
        ), f"{mutation.name}: killer {mutation.killer!r} is not a declared unit test"


def test_catalogue_covers_the_documented_regression_classes() -> None:
    names = {mutation.name for mutation in mutation_test.CATALOGUE}
    for required in (
        "left_join_to_inner_join",
        "full_join_to_left_join",
        "drop_ingest_date_predicate",
        "count_distinct_to_count",
        "reverse_reconciliation_arithmetic",
        "drop_coalesce_on_mart_side",
    ):
        assert required in names, f"missing required mutation: {required}"
    assert all(
        mutation.expect == mutation_test.KILLED for mutation in mutation_test.CATALOGUE
    ), "every catalogue mutation must be expected to die; survivors fail the gate"


def test_the_self_test_mutation_is_excluded_from_the_gate() -> None:
    """It is expected to survive, so including it would fail CI permanently."""
    assert mutation_test.SELF_TEST.expect == mutation_test.SURVIVED
    assert mutation_test.SELF_TEST not in mutation_test.CATALOGUE


@pytest.mark.integration
def test_harness_reports_a_surviving_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate is only trustworthy if it can actually see a survivor.

    Runs a real semantic mutation that no unit test covers, and requires the
    harness both to classify it as survived and to fail when that survival is
    unexpected."""

    result = mutation_test.evaluate(mutation_test.SELF_TEST)
    assert result.status == mutation_test.SURVIVED, result.detail

    # Same mutation, now declared as one that must die: the gate must exit 1.
    must_die = replace(mutation_test.SELF_TEST, expect=mutation_test.KILLED)
    monkeypatch.setattr(mutation_test, "CATALOGUE", [must_die])
    monkeypatch.setattr("sys.argv", ["mutation_test.py"])
    assert mutation_test.main() == 1, "a surviving mutation did not fail the gate"


@pytest.mark.integration
def test_harness_leaves_production_sql_untouched() -> None:
    """Mutations are applied to a copy; the real models must never change."""

    before = {
        mutation.path: (PROJECT / mutation.path).read_text(encoding="utf-8")
        for mutation in mutation_test.CATALOGUE
    }
    mutation_test.evaluate(mutation_test.CATALOGUE[0])
    for path, original in before.items():
        assert (PROJECT / path).read_text(
            encoding="utf-8"
        ) == original, f"{path} was modified in place"
