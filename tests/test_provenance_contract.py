"""NG-0.1's contract, exercised rather than described.

Two of these tests are the ones the item actually asks for: a negative test
proving high-cardinality identifiers are absent from the Prometheus label sets
this repository really declares, and proof that an envelope cannot fabricate an
identifier it does not have.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from common import provenance as p

REPO_ROOT = Path(__file__).resolve().parents[1]

METRIC_CONSTRUCTORS = {"Gauge", "Counter", "Histogram", "Summary"}

# Every module that declares Prometheus metrics. Listed rather than globbed: a
# new metrics surface should fail this test until it is deliberately added.
METRIC_SOURCES = (
    REPO_ROOT / "iceberg" / "common" / "ops.py",
    REPO_ROOT / "observability" / "postgres_exporter.py",
)


def declared_label_names(source: Path) -> dict[int, list[str]]:
    """Label names for every Prometheus metric declared in a module.

    Parsed rather than imported: importing the exporter would construct real
    collectors and, in one case, try to bind a socket. The property under test is
    what the source declares, and that is exactly what the parse sees.
    """

    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: dict[int, list[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name not in METRIC_CONSTRUCTORS:
            continue

        labels: ast.expr | None = None
        for keyword in node.keywords:
            if keyword.arg == "labelnames":
                labels = keyword.value
        if labels is None and len(node.args) >= 3:
            labels = node.args[2]
        if not isinstance(labels, (ast.List, ast.Tuple)):
            continue

        found[node.lineno] = [
            element.value
            for element in labels.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        ]

    return found


# --------------------------------------------------------------------------
# Cardinality-safe telemetry - the negative test NG-0.1 requires
# --------------------------------------------------------------------------


def test_the_metric_sources_this_test_guards_actually_exist() -> None:
    """Guards the guard: a moved file must fail loudly, not silently pass."""

    for source in METRIC_SOURCES:
        assert source.is_file(), f"{source} is listed as a metrics surface but is gone"


def test_no_declared_prometheus_label_is_high_cardinality() -> None:
    """`trace_id`, `load_id`, `cycle_id`, offsets and business keys stay out.

    Each would add one series per execution or per order, without bound. They
    belong in logs, trace attributes, exemplars, lineage facets or a table built
    for high-cardinality data - NG-0.1 lists all of those as fine.
    """

    offenders: list[str] = []
    checked = 0

    for source in METRIC_SOURCES:
        for line_no, labels in declared_label_names(source).items():
            checked += 1
            violations = p.cardinality_violations(labels)
            if violations:
                rel = source.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{line_no} declares {violations}")

    assert checked > 0, "parsed no metric declarations; the parser has drifted"
    assert not offenders, "high-cardinality Prometheus labels:\n" + "\n".join(offenders)


def test_the_cardinality_check_catches_a_forbidden_label() -> None:
    """The check has to be able to fail, or the test above proves nothing."""

    assert p.cardinality_violations(["source", "status"]) == []
    assert p.cardinality_violations(["source", "load_id"]) == ["load_id"]
    assert p.cardinality_violations(["TRACE_ID"]) == ["TRACE_ID"]
    assert p.cardinality_violations(["source", "cycle_id", "order_id"]) == [
        "cycle_id",
        "order_id",
    ]


def test_a_bare_string_is_rejected_rather_than_iterated_by_character() -> None:
    """`cardinality_violations("load_id")` must not silently check letters."""

    with pytest.raises(p.ProvenanceError):
        p.cardinality_violations("load_id")


# --------------------------------------------------------------------------
# A provenance envelope never fabricates
# --------------------------------------------------------------------------


def test_an_unavailable_identifier_is_absent_and_carries_a_reason() -> None:
    """The medallion's own case: a cycle with no Airflow run above it."""

    envelope = p.ProvenanceEnvelope(
        values={p.CYCLE_ID: "cyc-1", p.CODE_REVISION: "abc1234"},
        unknown={p.DAG_RUN_ID: "cycle was not launched by Airflow"},
    )

    assert envelope.to_dict() == {p.CYCLE_ID: "cyc-1", p.CODE_REVISION: "abc1234"}
    assert p.DAG_RUN_ID not in envelope.to_dict()
    assert envelope.reasons()[p.DAG_RUN_ID] == "cycle was not launched by Airflow"


def test_a_null_value_is_refused_because_absence_is_expressed_by_omission() -> None:
    with pytest.raises(p.ProvenanceError, match="null value"):
        p.ProvenanceEnvelope(values={p.DAG_RUN_ID: None})


def test_an_unknown_field_needs_a_reason() -> None:
    with pytest.raises(p.ProvenanceError, match="without a reason"):
        p.ProvenanceEnvelope(unknown={p.DAG_RUN_ID: "   "})


def test_a_field_cannot_be_both_known_and_unknown() -> None:
    with pytest.raises(p.ProvenanceError, match="both known and unknown"):
        p.ProvenanceEnvelope(
            values={p.CYCLE_ID: "cyc-1"}, unknown={p.CYCLE_ID: "not sure"}
        )


def test_a_name_outside_the_vocabulary_is_refused() -> None:
    """Two systems naming one concern differently is the failure NG-0.1 opens on."""

    with pytest.raises(p.ProvenanceError, match="canonical vocabulary"):
        p.ProvenanceEnvelope(values={"runId": "r-1"})


def test_required_identifiers_are_enforced_at_the_boundary() -> None:
    """A Bronze append knows its load id and its snapshot; a regression that
    drops one should fail there, not in a dashboard weeks later."""

    complete = p.ProvenanceEnvelope(
        values={p.LOAD_ID: "l-1", p.ICEBERG_SNAPSHOT_ID: 7, p.ICEBERG_TABLE: "bronze"}
    )
    assert complete.requires(p.LOAD_ID, p.ICEBERG_SNAPSHOT_ID) is complete

    with pytest.raises(p.ProvenanceError, match="required identifiers missing"):
        p.ProvenanceEnvelope(values={p.LOAD_ID: "l-1"}).requires(p.ICEBERG_SNAPSHOT_ID)


def test_an_envelope_is_immutable_once_built() -> None:
    envelope = p.ProvenanceEnvelope(values={p.CYCLE_ID: "cyc-1"})

    with pytest.raises(TypeError):
        envelope.values[p.CYCLE_ID] = "cyc-2"  # type: ignore[index]

    envelope.to_dict()[p.CYCLE_ID] = "cyc-2"
    assert envelope.to_dict()[p.CYCLE_ID] == "cyc-1", "to_dict must return a copy"


# --------------------------------------------------------------------------
# Iceberg snapshot is the structured-data version primitive
# --------------------------------------------------------------------------


@pytest.mark.architecture
def test_the_writer_stamps_its_load_id_into_the_snapshot() -> None:
    """The link that makes a snapshot addressable by the work that produced it.

    Without it, `iceberg.snapshot_id` and `load_id` are two facts about the same
    append with nothing joining them, and NG-0.1's end-to-end receipt has a gap
    exactly where the writer is.
    """

    source = (REPO_ROOT / "iceberg" / "writer" / "iceberg_writer.py").read_text(
        encoding="utf-8"
    )

    assert 'LOAD_ID_KEY = "load-id"' in source
    assert "snapshot_properties={LOAD_ID_KEY: load_id}" in source


@pytest.mark.architecture
def test_committed_compose_pins_every_image() -> None:
    """No floating `latest`: a rebuild must not silently change the platform."""

    floating: list[str] = []
    for compose in sorted(REPO_ROOT.glob("docker-compose*.yml")):
        for line_no, line in enumerate(
            compose.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped.startswith("image:"):
                continue
            reference = stripped.split("image:", 1)[1].strip()
            if reference.endswith(":latest") or (
                ":" not in reference.rsplit("/", 1)[-1] and "@" not in reference
            ):
                floating.append(f"{compose.name}:{line_no} {reference}")

    assert not floating, "unpinned images:\n" + "\n".join(floating)
