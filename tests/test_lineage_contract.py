"""NG-0.2's contract, exercised rather than described.

Lineage is unusually easy to test into meaninglessness: a graph assembled from
static topology renders perfectly and proves nothing. So the tests here are
weighted toward the properties that a wrong implementation would violate -
misattributed edges, duplicate owners, aliased datasets, and emission that can
reach the data path - and each guard is accompanied by proof that it can fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openlineage.client.event_v2 import RunState

from common import lineage
from common import provenance as prov


@pytest.fixture(autouse=True)
def _clean_registry():
    lineage.reset_edge_owners()
    yield
    lineage.reset_edge_owners()


@pytest.fixture
def file_emitter(tmp_path, monkeypatch):
    """An emitter wired to a real file transport.

    Deliberately not a mock: the transport is the part of the client this
    change depends on, and a mock would prove only that the mock was called.
    """
    log = tmp_path / "events.jsonl"
    monkeypatch.setenv("OPENLINEAGE__TRANSPORT__TYPE", "file")
    monkeypatch.setenv("OPENLINEAGE__TRANSPORT__LOG_FILE_PATH", str(log))
    monkeypatch.setenv("OPENLINEAGE__TRANSPORT__APPEND", "true")

    def events():
        if not log.exists():
            return []
        return [
            json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
        ]

    emitter = lineage.LineageEmitter("test.job", disabled=False)
    emitter.read_events = events  # type: ignore[attr-defined]
    return emitter


# --------------------------------------------------------------------------
# Dataset identity
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spelling",
    [
        "http://iceberg-rest:8181",
        "https://iceberg-rest:8181/",
        "iceberg-rest:8181",
        "iceberg-rest",
        "http://user:secret@iceberg-rest:8181",
        "HTTP://Iceberg-Rest:8181",
    ],
)
def test_endpoint_spellings_of_one_catalog_produce_one_dataset_identity(spelling):
    """One catalog addressed six ways is still one catalog.

    Left unnormalised each spelling would fork `bronze.orders` into a separate
    dataset, which is the alias defect NG-0.2 forbids by name.
    """
    assert lineage.iceberg_dataset(
        spelling, "bronze.orders"
    ) == lineage.iceberg_dataset("http://iceberg-rest:8181", "bronze.orders")


def test_credentials_never_survive_into_a_dataset_namespace():
    ref = lineage.iceberg_dataset("http://user:hunter2@iceberg-rest:8181", "bronze.o")
    assert "hunter2" not in ref.namespace
    assert "user" not in ref.namespace


@pytest.mark.parametrize("scheme", ["s3://", "s3a://", "s3n://", ""])
def test_object_store_schemes_normalise_to_one_bucket_identity(scheme):
    """The scheme records which client library wrote, not which bucket."""
    assert lineage.object_store_dataset(
        f"{scheme}de-practicum", "streaming/orders_raw"
    ) == lineage.object_store_dataset("de-practicum", "streaming/orders_raw")


def test_a_dataset_identity_contains_no_runtime_host_information():
    """The defect this guards is `socket.gethostname()` in a namespace.

    Under Compose that yields a container id, so every restart would rename
    every dataset the service emits.
    """
    import socket

    host = socket.gethostname()
    refs = [
        lineage.iceberg_dataset("http://iceberg-rest:8181", "bronze.orders"),
        lineage.object_store_dataset("de-practicum", "streaming/orders_raw"),
        lineage.kafka_dataset("kafka:9092", "orders"),
    ]
    for ref in refs:
        assert host.lower() not in f"{ref.namespace}/{ref.name}".lower()
        assert str(__import__("os").getpid()) not in ref.namespace


def test_dataset_naming_is_deterministic_across_calls():
    first = lineage.kafka_dataset("kafka:9092", "orders")
    second = lineage.kafka_dataset("kafka:9092", "orders")
    assert first == second
    assert hash(first) == hash(second)


def test_normalisation_does_not_collapse_genuinely_different_endpoints():
    """The guard above could be satisfied by returning a constant.

    Two different hosts must stay two datasets, or normalisation has become
    erasure.
    """
    assert lineage.iceberg_dataset(
        "http://catalog-a:8181", "t"
    ) != lineage.iceberg_dataset("http://catalog-b:8181", "t")
    assert lineage.object_store_dataset(
        "bucket-a", "p"
    ) != lineage.object_store_dataset("bucket-b", "p")


# --------------------------------------------------------------------------
# Edge ownership
# --------------------------------------------------------------------------


def test_two_boundaries_may_not_claim_one_output_dataset():
    """The negative test NG-0.2 requires for duplicate emitters."""
    silver = lineage.iceberg_dataset("http://iceberg-rest:8181", "silver.orders_clean")
    lineage.register_edge_owner(silver, "iceberg-medallion.bronze-to-silver")

    with pytest.raises(lineage.DuplicateEdgeOwner) as excinfo:
        lineage.register_edge_owner(silver, "some-other-service")

    message = str(excinfo.value)
    assert "iceberg-medallion.bronze-to-silver" in message
    assert "some-other-service" in message
    assert "silver.orders_clean" in message


def test_the_same_owner_may_reclaim_its_own_edge():
    """A service that restarts its loop must not fight itself."""
    gold = lineage.iceberg_dataset("http://iceberg-rest:8181", "gold.daily")
    lineage.register_edge_owner(gold, "medallion")
    lineage.register_edge_owner(gold, "medallion")
    assert lineage.edge_owner(gold) == "medallion"


def test_distinct_outputs_do_not_collide():
    a = lineage.iceberg_dataset("http://iceberg-rest:8181", "silver.a")
    b = lineage.iceberg_dataset("http://iceberg-rest:8181", "silver.b")
    lineage.register_edge_owner(a, "owner-a")
    lineage.register_edge_owner(b, "owner-b")
    assert lineage.edge_owner(a) == "owner-a"
    assert lineage.edge_owner(b) == "owner-b"


def test_the_real_services_do_not_claim_overlapping_edges():
    """The production registration actually holds.

    The registry only helps if the services are wired through it, so this
    performs both services' startup registration in one process.
    """
    from medallion import iceberg_medallion as med
    from writer import iceberg_writer as wr

    lineage.register_edge_owner(wr.BRONZE_DATASET, wr.LINEAGE_JOB)
    med.register_lineage_edges()  # must not raise


# --------------------------------------------------------------------------
# Emission never reaches the data path
# --------------------------------------------------------------------------


def test_an_unreachable_backend_is_counted_and_never_raised(monkeypatch):
    """A lineage outage must not become a data outage."""
    monkeypatch.setenv("OPENLINEAGE__TRANSPORT__TYPE", "http")
    monkeypatch.setenv("OPENLINEAGE__TRANSPORT__URL", "http://127.0.0.1:1")
    monkeypatch.setenv("OPENLINEAGE__TRANSPORT__TIMEOUT", "1")

    emitter = lineage.LineageEmitter("test.job", disabled=False)
    delivered = emitter.emit(
        run_id=lineage.run_id_for("load-1"),
        event_type=RunState.COMPLETE,
        outputs=[lineage.iceberg_dataset("http://iceberg-rest:8181", "bronze.orders")],
    )

    assert delivered is False
    assert emitter.failures == 1
    assert emitter.emitted == 0


def test_an_emitter_that_raises_internally_does_not_propagate():
    class Exploding:
        def emit(self, event):
            raise RuntimeError("transport exploded")

    emitter = lineage.LineageEmitter("test.job", client=Exploding(), disabled=False)
    assert emitter.emit(run_id="r", event_type=RunState.COMPLETE) is False
    assert emitter.failures == 1


def test_a_disabled_emitter_reports_no_delivery_and_no_failure():
    """Disabled is not the same as broken, and the counters must not conflate
    them - otherwise a deliberately disabled emitter looks like an outage."""
    emitter = lineage.LineageEmitter("test.job", disabled=True)
    assert emitter.emit(run_id="r", event_type=RunState.COMPLETE) is False
    assert emitter.failures == 0
    assert emitter.emitted == 0


def test_the_failure_counter_can_distinguish_success(file_emitter):
    """Proof the counter means something: the same assertions on a working
    transport must come out the other way."""
    assert (
        file_emitter.emit(run_id=lineage.run_id_for("ok"), event_type=RunState.COMPLETE)
        is True
    )
    assert file_emitter.failures == 0
    assert file_emitter.emitted == 1


def test_a_run_id_that_is_not_a_uuid_is_rejected_without_reaching_the_caller():
    """OpenLineage requires a UUID run id, and the client enforces it.

    That enforcement is why `run_id_for` exists: passing a raw `load_id`
    straight through would be refused at emit time. The refusal must still be
    absorbed rather than raised at a data-path caller.
    """
    emitter = lineage.LineageEmitter("test.job", disabled=False)
    assert emitter.emit(run_id="not-a-uuid", event_type=RunState.COMPLETE) is False
    assert emitter.failures == 1


# --------------------------------------------------------------------------
# Event content
# --------------------------------------------------------------------------


def test_an_emitted_event_carries_the_datasets_and_the_provenance_facet(file_emitter):
    envelope = prov.ProvenanceEnvelope(
        values={prov.LOAD_ID: "load-abc", prov.ICEBERG_TABLE: "bronze.orders"},
        unknown={prov.DAG_RUN_ID: "not launched by Airflow"},
    )
    assert file_emitter.emit(
        run_id=lineage.run_id_for("load-abc"),
        event_type=RunState.COMPLETE,
        inputs=[lineage.object_store_dataset("de-practicum", "streaming/orders_raw")],
        outputs=[lineage.iceberg_dataset("http://iceberg-rest:8181", "bronze.orders")],
        envelope=envelope,
    )

    (event,) = file_emitter.read_events()
    assert event["eventType"] == "COMPLETE"
    assert event["inputs"][0]["namespace"] == "s3://de-practicum"
    assert event["inputs"][0]["name"] == "streaming/orders_raw"
    assert event["outputs"][0]["namespace"] == "iceberg://iceberg-rest"
    assert event["outputs"][0]["name"] == "bronze.orders"

    facet = event["run"]["facets"]["provenance"]
    assert facet["identifiers"]["load_id"] == "load-abc"
    assert facet["absent"]["airflow.dag_run_id"] == "not launched by Airflow"
    # The never-fabricate rule survives the trip onto the event.
    assert "airflow.dag_run_id" not in facet["identifiers"]


def test_a_run_id_is_derived_from_the_platform_identifier_so_a_retry_is_one_run():
    """Two emissions for one load must be one lineage run, not two."""
    assert lineage.run_id_for("load-abc") == lineage.run_id_for("load-abc")
    assert lineage.run_id_for("load-abc") != lineage.run_id_for("load-def")
    # OpenLineage requires a UUID; a raw load_id would be rejected downstream.
    import uuid

    uuid.UUID(lineage.run_id_for("load-abc"))


def test_a_facet_cannot_carry_an_identifier_outside_the_vocabulary():
    """NG-0.1's refusal is what stops lineage inventing its own names."""
    with pytest.raises(prov.ProvenanceError):
        lineage.provenance_facet(
            prov.ProvenanceEnvelope(values={"lineage.invented_field": "x"})
        )


# --------------------------------------------------------------------------
# The boundaries themselves
# --------------------------------------------------------------------------


def test_the_writer_claims_the_landing_to_bronze_edge_and_not_the_kafka_edge(
    file_emitter,
):
    """The central correctness property of this change.

    Bronze rows carry `kafka_offset`, so a Kafka-to-Bronze edge is derivable
    here. The writer never read Kafka, and emitting that edge would make the
    graph lie about which job did what.
    """
    from writer import iceberg_writer as wr

    class FakeTable:
        metadata = type(
            "M",
            (),
            {
                "snapshots": [
                    type(
                        "S",
                        (),
                        {
                            "snapshot_id": 991,
                            "summary": type(
                                "Sum", (), {"additional_properties": {"load-id": "L1"}}
                            )(),
                        },
                    )()
                ]
            },
        )()

    assert wr.emit_ingest_lineage(file_emitter, "L1", FakeTable()) is True
    (event,) = file_emitter.read_events()

    inputs = {(d["namespace"], d["name"]) for d in event["inputs"]}
    outputs = {(d["namespace"], d["name"]) for d in event["outputs"]}
    assert outputs == {("iceberg://iceberg-rest", "bronze.orders")}
    assert inputs == {("s3://de-practicum", "streaming/orders_raw")}
    assert not any(ns.startswith("kafka://") for ns, _ in inputs)

    facet = event["run"]["facets"]["provenance"]
    assert facet["identifiers"]["load_id"] == "L1"
    assert facet["identifiers"]["iceberg.snapshot_id"] == 991
    # Absences are declared with reasons, not omitted.
    assert "airflow.dag_run_id" in facet["absent"]
    assert "trace_id" in facet["absent"]


def test_the_writer_declares_an_unreadable_snapshot_absent_rather_than_omitting_it(
    file_emitter,
):
    from writer import iceberg_writer as wr

    class NoSnapshots:
        metadata = type("M", (), {"snapshots": []})()

    assert wr.emit_ingest_lineage(file_emitter, "L2", NoSnapshots()) is True
    (event,) = file_emitter.read_events()
    facet = event["run"]["facets"]["provenance"]
    assert "iceberg.snapshot_id" not in facet["identifiers"]
    assert facet["absent"]["iceberg.snapshot_id"]


def test_a_snapshot_read_failure_in_the_writer_never_reaches_the_caller(file_emitter):
    from writer import iceberg_writer as wr

    class Hostile:
        @property
        def metadata(self):
            raise RuntimeError("catalog metadata unavailable")

    # Returns normally; the identifier is declared absent instead.
    assert wr.emit_ingest_lineage(file_emitter, "L3", Hostile()) is True
    (event,) = file_emitter.read_events()
    assert event["run"]["facets"]["provenance"]["absent"]["iceberg.snapshot_id"]


def test_the_medallion_emits_both_transformations_with_distinct_state_fields(
    monkeypatch, file_emitter
):
    """Bronze-to-Silver and Silver-to-Gold are separately observable.

    The event must also distinguish the state it *read* from the state it
    *wrote*: one snapshot field cannot carry both, which is why NG-0.2 added
    `iceberg.source_snapshot_id` to the vocabulary.
    """
    from medallion import iceberg_medallion as med

    monkeypatch.setattr(med, "_bronze_snapshot_id", lambda c: 100)
    monkeypatch.setattr(med, "_silver_snapshot_id", lambda c: 200)
    monkeypatch.setattr(med, "_gold_snapshot_id", lambda c: 300)
    monkeypatch.setattr(med, "_lineage_emitter", lambda name: file_emitter)

    assert med.emit_cycle_lineage(catalog=None, cycle_id="cyc-1") == 2
    silver_event, gold_event = file_emitter.read_events()

    assert silver_event["inputs"][0]["name"] == "bronze.orders"
    assert silver_event["outputs"][0]["name"] == "silver.orders_clean"
    silver_ids = silver_event["run"]["facets"]["provenance"]["identifiers"]
    assert silver_ids["iceberg.source_snapshot_id"] == 100
    assert silver_ids["iceberg.snapshot_id"] == 200
    assert silver_ids["cycle_id"] == "cyc-1"

    assert gold_event["inputs"][0]["name"] == "silver.orders_clean"
    assert gold_event["outputs"][0]["name"] == "gold.orders_daily_metrics"
    gold_ids = gold_event["run"]["facets"]["provenance"]["identifiers"]
    assert gold_ids["iceberg.source_snapshot_id"] == 200
    assert gold_ids["iceberg.snapshot_id"] == 300


def test_a_medallion_snapshot_that_cannot_be_read_becomes_a_declared_absence(
    monkeypatch, file_emitter
):
    from medallion import iceberg_medallion as med

    def unreachable(_catalog):
        raise RuntimeError("REST catalog unavailable")

    monkeypatch.setattr(med, "_bronze_snapshot_id", unreachable)
    monkeypatch.setattr(med, "_silver_snapshot_id", lambda c: 200)
    monkeypatch.setattr(med, "_gold_snapshot_id", lambda c: 300)
    monkeypatch.setattr(med, "_lineage_emitter", lambda name: file_emitter)

    # The cycle's lineage still emits; the unreadable identifier is declared.
    assert med.emit_cycle_lineage(catalog=None, cycle_id="cyc-2") == 2
    silver_event = file_emitter.read_events()[0]
    facet = silver_event["run"]["facets"]["provenance"]
    assert "iceberg.source_snapshot_id" not in facet["identifiers"]
    assert facet["absent"]["iceberg.source_snapshot_id"]


def test_the_new_vocabulary_field_is_registered_everywhere_it_must_be():
    """A field added to one set and not the others is a silent hole.

    `iceberg.source_snapshot_id` is per-execution and unbounded, so omitting it
    from the high-cardinality set would let it become a Prometheus label.
    """
    assert prov.ICEBERG_SOURCE_SNAPSHOT_ID in prov.CANONICAL_FIELDS
    assert prov.ICEBERG_SOURCE_SNAPSHOT_ID in prov.HIGH_CARDINALITY_FIELDS
    assert "source_snapshot_id" in prov.FORBIDDEN_LABEL_NAMES
    assert prov.cardinality_violations(["source_snapshot_id"]) == ["source_snapshot_id"]


# --------------------------------------------------------------------------
# Guarding the guards
# --------------------------------------------------------------------------


def test_the_documented_lineage_record_still_describes_the_emitted_surface():
    """`docs/LINEAGE.md` is the pre-existing descriptive record of lineage in
    this repository, and NG-0.2 changed what it describes.

    The assertions below are the parts that would silently rot: the claim that
    OpenLineage emission is unimplemented, and the record of the one edge this
    change could not close.
    """
    doc = Path(__file__).resolve().parents[1] / "docs" / "LINEAGE.md"
    assert doc.exists(), f"{doc} is missing"
    text = doc.read_text(encoding="utf-8")

    assert "OpenLineage emission is not implemented" not in text, (
        "the document still claims emission is unimplemented, which NG-0.2 " "changed"
    )
    # The known hole must stay written down, with the version that causes it.
    assert "spark40" in text
    assert "4.2.0" in text
    # The three emitting boundaries are named.
    for job in (
        "iceberg-writer.landing-to-bronze",
        "iceberg-medallion.bronze-to-silver",
        "iceberg-medallion.silver-to-gold",
    ):
        assert job in text, f"{job} is not documented"
