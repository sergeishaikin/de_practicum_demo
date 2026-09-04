"""The H1 OTel acceptance gate must be able to reject a bad run.

The gate this replaces could not. It hashed ``expected_pipeline(build_fixture())``
- a pure function of the test source - once per phase and compared the three
digests, so ``canonical parity mismatch`` was unreachable and
``canonical_parity: PASS`` was printed on every run that got that far.

Every test below is a deliberate single-invariant break: it takes an otherwise
valid three-phase bundle, damages exactly one property, and asserts the
validator rejects it. A gate nobody has watched fail is not evidence, so the
failures are pinned here rather than demonstrated once by hand.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import build_otel_receipt, capture_container_resources
from scripts import validate_otel_acceptance as validator

ROOT = Path(__file__).resolve().parents[1]

CONTAINERS = (
    "de-demo-otel-collector",
    "de-demo-orders-streaming",
    "de-demo-iceberg-writer",
    "de-demo-iceberg-medallion",
)

CONTRACT = {
    "kafka_events": 101,
    "landing_rows": 99,
    "bronze_rows": 99,
    "bronze_distinct_orders": 95,
    "silver_rows": 95,
    "duplicates_removed": 4,
    "gold_row_count": 16,
    "gold_orders_count": 95,
    "gold_total_revenue": "1234.000000",
}

GOLD = [
    ["2026-08-07", "ES", "paid", "10", "100.000000", "10.000000", "3"],
    ["2026-08-07", "UK", "delivered", "9", "90.000000", "10.000000", "3"],
]


def _stats() -> dict:
    return {"Name": "c", "CPUPerc": "0.50%", "MemUsage": "10MiB / 1GiB"}


def _record(state: str) -> dict:
    return {
        "expected_state": state,
        "observed_state": state,
        "stats": _stats() if state == "running" else None,
    }


def resources(phase: str, stage: str, collector: str, worker: str) -> dict:
    return {
        "phase": phase,
        "stage": stage,
        "containers": {
            "de-demo-otel-collector": _record(collector),
            "de-demo-orders-streaming": _record("running"),
            "de-demo-iceberg-writer": _record(worker),
            "de-demo-iceberg-medallion": _record(worker),
        },
    }


def make_receipt(phase: str, contract: dict | None = None, gold=None) -> dict:
    observed = dict(contract or CONTRACT)
    snapshot = [list(row) for row in (gold or GOLD)]
    outage = phase == "outage"
    return {
        "phase": phase,
        "otel_enabled": phase != "off",
        "collector_outage": outage,
        "pytest_e2e_passed": True,
        "git_sha": "a" * 40,
        "run_id": f"run-{phase}",
        "namespace": f"e2e_{phase}",
        "duration_seconds": 42.5,
        "expected_contract": dict(CONTRACT),
        "expected_contract_sha256": validator.digest(dict(CONTRACT)),
        "observed_contract": observed,
        "observed_contract_sha256": validator.digest(observed),
        "observed_gold_snapshot": snapshot,
        "observed_gold_sha256": validator.digest(snapshot),
        "otel_wal_bytes_before": 0,
        "otel_wal_bytes_after": 8192,
        "resources_before": resources(phase, "before", "running", "running"),
        "resources_after": resources(
            phase, "after", "stopped" if outage else "running", "stopped"
        ),
    }


def write_bundle(tmp_path: Path, receipts: dict[str, dict]) -> list[str]:
    paths = []
    for phase, receipt in receipts.items():
        path = tmp_path / f"otel-{phase}-receipt.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        paths.append(str(path))
    return paths


def default_bundle() -> dict[str, dict]:
    return {phase: make_receipt(phase) for phase in validator.PHASES}


def run(tmp_path: Path, receipts: dict[str, dict], *, require_sha: bool = True) -> int:
    argv = write_bundle(tmp_path, receipts)
    if require_sha:
        argv.append("--require-git-sha")
    return validator.main(argv)


# --------------------------------------------------------------------------- #
# The baseline must pass, or every rejection below proves nothing.
# --------------------------------------------------------------------------- #
def test_valid_bundle_is_accepted(tmp_path: Path) -> None:
    assert run(tmp_path, default_bundle()) == 0


# --------------------------------------------------------------------------- #
# Transparency: the phases must be comparable to each other, and the comparison
# must be capable of disagreeing. This is the defect the whole change exists for.
# --------------------------------------------------------------------------- #
def test_a_single_diverging_observed_field_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    drifted = dict(CONTRACT)
    drifted["silver_rows"] = CONTRACT["silver_rows"] - 1
    receipts["on"] = make_receipt("on", contract=drifted)
    assert run(tmp_path, receipts) == 1


def test_a_single_diverging_gold_row_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    mutated = [list(row) for row in GOLD]
    mutated[0][4] = "999.000000"
    receipts["outage"] = make_receipt("outage", gold=mutated)
    assert run(tmp_path, receipts) == 1


def test_gold_parity_catches_reordered_rows_with_equal_totals(tmp_path: Path) -> None:
    """Aggregates alone would not notice this; the row snapshot must."""
    receipts = default_bundle()
    swapped = [list(row) for row in GOLD]
    swapped[0][1], swapped[1][1] = swapped[1][1], swapped[0][1]
    receipts["on"] = make_receipt("on", gold=swapped)
    assert run(tmp_path, receipts) == 1


def test_three_copies_of_one_run_are_rejected(tmp_path: Path) -> None:
    """Identical digests must come from three runs, not one receipt duplicated."""
    receipts = {phase: make_receipt(phase) for phase in validator.PHASES}
    for phase in validator.PHASES:
        receipts[phase]["run_id"] = "same-run"
    assert run(tmp_path, receipts) == 1


# --------------------------------------------------------------------------- #
# Correctness: observed must equal predicted, and the digests must be the
# digests of the payloads that carry them.
# --------------------------------------------------------------------------- #
def test_observed_diverging_from_expected_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    drifted = dict(CONTRACT)
    drifted["gold_row_count"] = 99
    for phase in validator.PHASES:
        receipts[phase] = make_receipt(phase, contract=drifted)
    assert run(tmp_path, receipts) == 1


def test_tampered_observed_digest_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    receipts["on"]["observed_contract_sha256"] = "0" * 64
    assert run(tmp_path, receipts) == 1


def test_tampered_gold_digest_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    receipts["outage"]["observed_gold_sha256"] = "0" * 64
    assert run(tmp_path, receipts) == 1


@pytest.mark.parametrize("field", ["observed_contract", "observed_gold_snapshot"])
def test_empty_observation_is_rejected(tmp_path: Path, field: str) -> None:
    receipts = default_bundle()
    receipts["off"][field] = type(receipts["off"][field])()
    assert run(tmp_path, receipts) == 1


# --------------------------------------------------------------------------- #
# Bundle completeness and phase identity.
# --------------------------------------------------------------------------- #
def test_a_missing_phase_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    del receipts["outage"]
    assert run(tmp_path, receipts) == 1


def test_an_empty_receipt_file_is_rejected(tmp_path: Path) -> None:
    paths = write_bundle(tmp_path, default_bundle())
    Path(paths[0]).write_text("", encoding="utf-8")
    assert validator.main(paths + ["--require-git-sha"]) == 1


def test_phases_from_different_commits_are_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    receipts["on"]["git_sha"] = "b" * 40
    assert run(tmp_path, receipts) == 1


def test_missing_commit_is_rejected_when_required(tmp_path: Path) -> None:
    receipts = default_bundle()
    for phase in validator.PHASES:
        receipts[phase]["git_sha"] = ""
    assert run(tmp_path, receipts) == 1


@pytest.mark.parametrize(
    "phase,field",
    [("off", "otel_enabled"), ("on", "collector_outage"), ("outage", "otel_enabled")],
)
def test_phase_matrix_violations_are_rejected(
    tmp_path: Path, phase: str, field: str
) -> None:
    receipts = default_bundle()
    receipts[phase][field] = not receipts[phase][field]
    assert run(tmp_path, receipts) == 1


# --------------------------------------------------------------------------- #
# Resource evidence: "not measured" must never read as a measurement.
# --------------------------------------------------------------------------- #
def test_outage_phase_declaring_a_running_collector_is_rejected(
    tmp_path: Path,
) -> None:
    """The declaration itself is checked, not merely its self-consistency.

    A phase that never stopped the Collector but recorded `running/running`
    is internally coherent and proves nothing about a Collector outage.
    """
    receipts = default_bundle()
    receipts["outage"]["resources_after"] = resources(
        "outage", "after", "running", "stopped"
    )
    assert run(tmp_path, receipts) == 1


def test_running_container_without_stats_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    block = receipts["on"]["resources_after"]
    block["containers"]["de-demo-orders-streaming"]["stats"] = None
    assert run(tmp_path, receipts) == 1


def test_stats_missing_a_required_field_are_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    block = receipts["on"]["resources_before"]
    block["containers"]["de-demo-iceberg-writer"]["stats"] = {"Name": "c"}
    assert run(tmp_path, receipts) == 1


def test_stopped_container_carrying_stats_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    block = receipts["off"]["resources_after"]
    block["containers"]["de-demo-iceberg-writer"]["stats"] = _stats()
    assert run(tmp_path, receipts) == 1


def test_state_disagreement_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    block = receipts["off"]["resources_before"]
    block["containers"]["de-demo-otel-collector"]["observed_state"] = "stopped"
    assert run(tmp_path, receipts) == 1


def test_a_dropped_container_record_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    del receipts["on"]["resources_after"]["containers"]["de-demo-iceberg-medallion"]
    assert run(tmp_path, receipts) == 1


def test_mislabelled_resource_stage_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    receipts["on"]["resources_after"]["stage"] = "before"
    assert run(tmp_path, receipts) == 1


# --------------------------------------------------------------------------- #
# WAL and duration: an absent measurement is not a zero.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [None, -1, "0", 1.5, True],
    ids=["null", "negative", "text", "float", "bool"],
)
def test_non_integer_wal_values_are_rejected(tmp_path: Path, value: object) -> None:
    receipts = default_bundle()
    receipts["on"]["otel_wal_bytes_after"] = value
    assert run(tmp_path, receipts) == 1


@pytest.mark.parametrize("value", [0, -3.0, None, "12"])
def test_non_positive_duration_is_rejected(tmp_path: Path, value: object) -> None:
    receipts = default_bundle()
    receipts["off"]["duration_seconds"] = value
    assert run(tmp_path, receipts) == 1


def test_a_failed_pytest_phase_is_rejected(tmp_path: Path) -> None:
    receipts = default_bundle()
    receipts["outage"]["pytest_e2e_passed"] = False
    assert run(tmp_path, receipts) == 1


# --------------------------------------------------------------------------- #
# Receipt assembly refuses to invent inputs it did not get.
# --------------------------------------------------------------------------- #
def _observed_evidence() -> dict:
    return {
        "run_id": "r1",
        "namespace": "e2e_r1",
        "git_sha": "a" * 40,
        "expected_contract": dict(CONTRACT),
        "expected_contract_sha256": validator.digest(dict(CONTRACT)),
        "observed_contract": dict(CONTRACT),
        "observed_contract_sha256": validator.digest(dict(CONTRACT)),
        "observed_gold_snapshot": GOLD,
        "observed_gold_sha256": validator.digest(GOLD),
    }


def _receipt_args(tmp_path: Path, **overrides) -> list[str]:
    files = {
        "observed": ("observed.json", json.dumps(_observed_evidence())),
        "duration-file": ("duration.txt", "12.5\n"),
        "wal-before": ("wal-before.txt", "0\n"),
        "wal-after": ("wal-after.txt", "4096\n"),
        "resources-before": (
            "res-before.json",
            json.dumps(resources("off", "before", "running", "running")),
        ),
        "resources-after": (
            "res-after.json",
            json.dumps(resources("off", "after", "running", "stopped")),
        ),
    }
    argv = ["--phase", "off", "--otel-enabled", "0", "--collector-outage", "0"]
    for flag, (name, content) in files.items():
        path = tmp_path / name
        path.write_text(overrides.get(flag, content), encoding="utf-8")
        argv += [f"--{flag}", str(path)]
    return argv + ["--output", str(tmp_path / "receipt.json")]


def test_receipt_assembly_accepts_complete_inputs(tmp_path: Path) -> None:
    assert build_otel_receipt.main(_receipt_args(tmp_path)) == 0
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["otel_wal_bytes_after"] == 4096
    assert receipt["observed_contract"] == CONTRACT


@pytest.mark.parametrize(
    "flag,broken",
    [
        ("wal-before", ""),
        ("wal-before", "\n"),
        ("wal-before", "0 bytes\n"),
        ("wal-after", "-1\n"),
        ("duration-file", "0\n"),
        ("duration-file", "not-a-number\n"),
        ("observed", "{}"),
        ("observed", "not json"),
    ],
)
def test_receipt_assembly_refuses_unusable_inputs(
    tmp_path: Path, flag: str, broken: str
) -> None:
    assert build_otel_receipt.main(_receipt_args(tmp_path, **{flag: broken})) == 1
    assert not (tmp_path / "receipt.json").exists()


# --------------------------------------------------------------------------- #
# Resource capture: a daemon error must not become evidence.
# --------------------------------------------------------------------------- #
def test_capture_records_stats_for_a_running_container(monkeypatch) -> None:
    def fake(*args: str):
        if args[0] == "inspect":
            return 0, "true", ""
        return 0, json.dumps(_stats()), ""

    monkeypatch.setattr(capture_container_resources, "_docker", fake)
    containers, errors = capture_container_resources.capture({"c": "running"})
    assert errors == []
    assert containers["c"]["stats"]["CPUPerc"] == "0.50%"


def test_capture_rejects_a_container_that_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        capture_container_resources, "_docker", lambda *a: (1, "", "No such object")
    )
    containers, errors = capture_container_resources.capture({"c": "running"})
    assert containers["c"]["observed_state"] == "absent"
    assert errors and "expected running, observed absent" in errors[0]


def test_capture_rejects_stats_that_are_not_json(monkeypatch) -> None:
    def fake(*args: str):
        if args[0] == "inspect":
            return 0, "true", ""
        return 0, "Error response from daemon: No such container", ""

    monkeypatch.setattr(capture_container_resources, "_docker", fake)
    containers, errors = capture_container_resources.capture({"c": "running"})
    assert containers["c"]["stats"] is None
    assert errors and "did not return JSON" in errors[0]


def test_capture_records_a_deliberately_stopped_container_without_stats(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        capture_container_resources, "_docker", lambda *a: (0, "false", "")
    )
    containers, errors = capture_container_resources.capture({"c": "stopped"})
    assert errors == []
    assert containers["c"] == {
        "expected_state": "stopped",
        "observed_state": "stopped",
        "stats": None,
    }


# --------------------------------------------------------------------------- #
# The two halves of the contract must keep asking the same questions.
# --------------------------------------------------------------------------- #
def _returned_dict_keys(function: ast.FunctionDef) -> set[str]:
    for node in ast.walk(function):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return {
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
    raise AssertionError(f"{function.name} does not return a dict literal")


def test_expected_and_observed_contracts_cover_identical_keys() -> None:
    """A prediction with no observable counterpart cannot be part of a parity claim.

    Read statically so this holds without a running stack: the point is that the
    two projections cannot drift apart unnoticed, not that either one runs here.
    """
    tree = ast.parse(
        (ROOT / "tests" / "e2e" / "test_lakehouse_e2e.py").read_text(encoding="utf-8")
    )
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in ("expected_contract", "observed_contract")
    }
    assert set(functions) == {"expected_contract", "observed_contract"}
    predicted = _returned_dict_keys(functions["expected_contract"])
    observed = _returned_dict_keys(functions["observed_contract"])
    assert predicted == observed
    assert predicted == set(CONTRACT), "this suite's fixture drifted from the contract"


def test_acceptance_evidence_is_observed_not_re_derived() -> None:
    """The workflow must not rebuild the contract from the test source again.

    The original defect was an `ast.parse` of the E2E module inside the
    workflow, which made the parity digest a function of the checked-out file
    rather than of the run. Pinned by substring so it cannot come back quietly.
    """
    workflow = (ROOT / ".github/workflows/ci-h1-clean.yml").read_text(encoding="utf-8")
    assert "ast.parse" not in workflow
    assert "canonical_contract_sha256" not in workflow
    assert "E2E_OBSERVED_EVIDENCE_PATH" in workflow
    assert "scripts/validate_otel_acceptance.py" in workflow
    # PASS is the validator's word to say, not the shell's.
    assert "resource_delta" not in workflow


def _acceptance_step() -> str:
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci-h1-clean.yml").read_text(encoding="utf-8")
    )
    step = next(
        s
        for s in workflow["jobs"]["otel-acceptance"]["steps"]
        if s.get("name", "").startswith("Run bounded OFF")
    )
    return step["run"]


def test_wal_measurement_has_no_silent_zero_fallback() -> None:
    """`echo 0` on an unmeasurable WAL made "absent" and "empty" one number.

    Pinned by substring for the same reason the dbt freshness gate is: the
    fallback reads as harmless defensive shell, and reintroducing it would make
    the WAL column of every receipt meaningless without failing anything.
    """
    step = _acceptance_step()
    assert "|| echo 0" not in step
    assert "then echo 0; return; fi" not in step
    # `pipefail` is what lets a failing `docker run` reach the guard at all.
    assert "set -euo pipefail" in step
    assert 'if ! [[ "$bytes" =~ ^[0-9]+$ ]]; then' in step


def test_the_acceptance_step_never_swallows_a_failure() -> None:
    """`|| true` belongs in teardown and best-effort diagnostics, nowhere else.

    Every command in this step either measures something the receipt asserts or
    sets up the run that produces it, so a swallowed error here is a silently
    wrong receipt rather than a missing log line.
    """
    executable = [
        line
        for line in _acceptance_step().splitlines()
        if not line.lstrip().startswith("#")
    ]
    offenders = [line.strip() for line in executable if "|| true" in line]
    assert not offenders, offenders


def test_the_shared_network_is_created_from_a_known_state() -> None:
    workflow = (ROOT / ".github/workflows/ci-h1-clean.yml").read_text(encoding="utf-8")
    assert "docker network create de_demo_net || true" not in workflow
    assert "if ! docker network inspect de_demo_net >/dev/null 2>&1; then" in workflow


def test_resource_evidence_is_captured_as_validated_json() -> None:
    step = _acceptance_step()
    assert "scripts/capture_container_resources.py" in step
    # The shape that let `Error response from daemon: ...` become evidence.
    assert "docker stats --no-stream --format '{{.Name}}" not in step


def test_every_phase_artifact_is_named_in_the_bundle_gate() -> None:
    """A wildcard upload path is not an evidence contract."""
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/ci-h1-clean.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["otel-acceptance"]["steps"]
    gate = next(
        s for s in steps if s.get("name", "").startswith("Assert the acceptance")
    )
    upload = next(s for s in steps if s.get("name", "").startswith("Upload OTel"))
    for artifact in (
        "receipt.json",
        "observed.json",
        "resources-before.json",
        "resources-after.json",
        "wal-before.txt",
        "wal-after.txt",
        "duration.txt",
        "junit.xml",
    ):
        assert artifact in gate["run"], artifact
    assert upload["with"]["if-no-files-found"] == "error"


# --------------------------------------------------------------------------- #
# One SQL NULL, one spelling. The first hardened H1 run recorded a numeric NULL
# as "null" beside a country NULL rendered "<null>", because Trino's `format`
# returns the string "null" for a NULL argument and the wrapping `coalesce`
# therefore never fired.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spelling", ["null", "NULL", "None", "", "NaN", "nil"])
def test_non_canonical_null_spelling_in_gold_is_rejected(
    tmp_path: Path, spelling: str
) -> None:
    receipts = default_bundle()
    mutated = [list(row) for row in GOLD]
    mutated[0][4] = spelling  # total_amount, the column that actually regressed
    for phase in validator.PHASES:
        receipts[phase] = make_receipt(phase, gold=mutated)
    assert run(tmp_path, receipts) == 1


def test_the_canonical_null_sentinel_is_accepted(tmp_path: Path) -> None:
    """The check must reject other spellings without rejecting the real one."""
    receipts = default_bundle()
    mutated = [list(row) for row in GOLD]
    mutated[0][1] = validator.NULL_SENTINEL  # country
    mutated[0][4] = validator.NULL_SENTINEL  # total_amount
    for phase in validator.PHASES:
        receipts[phase] = make_receipt(phase, gold=mutated)
    assert run(tmp_path, receipts) == 0


def test_unrendered_gold_cells_are_rejected(tmp_path: Path) -> None:
    """A JSON null or a number would hash differently than a rendered string."""
    receipts = default_bundle()
    mutated = [list(row) for row in GOLD]
    mutated[0][3] = 10
    for phase in validator.PHASES:
        receipts[phase] = make_receipt(phase, gold=mutated)
    assert run(tmp_path, receipts) == 1


def test_gold_snapshot_sql_tests_for_null_before_rendering() -> None:
    """`coalesce(format(...), ...)` is the shape that shipped the defect.

    Pinned by substring: the bug is invisible in review precisely because the
    coalesce looks like it handles the NULL, so a future simplification back to
    it must fail here rather than in an artifact nobody opens.
    """
    source = (ROOT / "tests" / "e2e" / "test_lakehouse_e2e.py").read_text(
        encoding="utf-8"
    )
    start = source.index("GOLD_SNAPSHOT_SQL")
    sql = source[start : source.index('"""', source.index('"""', start) + 3)]
    assert "coalesce(format(" not in sql
    for column in (
        "event_date",
        "country",
        "status",
        "orders_count",
        "total_amount",
        "avg_amount",
        "distinct_customers",
    ):
        assert f"CASE WHEN {column} IS NULL" in sql, column
