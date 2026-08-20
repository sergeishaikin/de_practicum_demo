"""NG-0.2's receipt: the lineage graph, read back out of a running stack.

The item's acceptance is "a live lineage receipt showing an actual path". That
is only meaningful if the events come from the services themselves rather than
from the test, so this reads the emitted event stream out of the shared lineage
volume and reconstructs the graph from it.

What it proves and what it does not:

- **Proves** that the writer and the medallion emitted events for work they
  actually performed, that those events form a connected landing -> Bronze ->
  Silver -> Gold path, and that each edge has exactly one owning job.
- **Does not prove** the Kafka-to-landing edge, which is not emitted at all.
  That absence is asserted here deliberately: the correct behaviour for a
  boundary with no working integration is to stay silent rather than to invent
  the edge, and a test that merely omitted the check would not notice if some
  later change started fabricating it.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_DIR = REPO_ROOT / "artifacts" / "lineage"

CONTAINER = "de-demo-iceberg-writer"
EVENT_LOG = "/lineage/events.jsonl"

WRITER_JOB = "iceberg-writer.landing-to-bronze"
SILVER_JOB = "iceberg-medallion.bronze-to-silver"
GOLD_JOB = "iceberg-medallion.silver-to-gold"

# The medallion cycles on a 60s interval, so the Gold edge is the slowest to
# appear. Bounded rather than open-ended: a receipt that waits forever is a
# hung job, not evidence.
TIMEOUT_SECONDS = 300
POLL_SECONDS = 10


def _emitters_are_running() -> bool:
    """Whether the services that emit lineage are actually up.

    Not every integration stack is the full one: `ci-integration.yml` starts
    only MinIO, the REST catalog and Trino, so the emitting services are absent
    there and this receipt has nothing to read. Skipping with a reason is the
    honest outcome; polling for five minutes and failing would report a missing
    stack as a broken emitter.

    `test_the_receipt_targets_the_container_compose_actually_defines` keeps this
    from degrading into a permanent silent skip if the container is renamed.
    """
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name=^{CONTAINER}$",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and CONTAINER in result.stdout


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _emitters_are_running(),
        reason=(
            f"{CONTAINER} is not running: this stack does not include the "
            "lineage-emitting services, so there is no emitted event stream to "
            "read. The receipt runs in the H1 clean-stack workflow."
        ),
    ),
]


def _read_events() -> list[dict]:
    """The emitted event stream, as the services wrote it."""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "cat", EVENT_LOG],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        # The file does not exist until the first event is emitted.
        return []
    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _wait_for_jobs(required: set[str]) -> list[dict]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    events: list[dict] = []
    seen: set[str] = set()
    while time.monotonic() < deadline:
        events = _read_events()
        seen = {event["job"]["name"] for event in events}
        if required <= seen:
            return events
        time.sleep(POLL_SECONDS)
    pytest.fail(
        f"lineage events for {sorted(required - seen)} did not appear within "
        f"{TIMEOUT_SECONDS}s. Seen jobs: {sorted(seen)}; {len(events)} events total."
    )


@pytest.fixture(scope="module")
def emitted_events() -> list[dict]:
    return _wait_for_jobs({WRITER_JOB, SILVER_JOB, GOLD_JOB})


def _edges(events: list[dict], job: str) -> list[tuple[str, str]]:
    """(input, output) dataset names for one job's events."""
    pairs = []
    for event in events:
        if event["job"]["name"] != job:
            continue
        for source in event.get("inputs") or []:
            for target in event.get("outputs") or []:
                pairs.append((source["name"], target["name"]))
    return pairs


def test_the_emitted_events_form_a_connected_landing_to_gold_path(emitted_events):
    """The acceptance graph, minus the hop that has no integration."""
    writer_edges = set(_edges(emitted_events, WRITER_JOB))
    silver_edges = set(_edges(emitted_events, SILVER_JOB))
    gold_edges = set(_edges(emitted_events, GOLD_JOB))

    assert ("streaming/orders_raw", "bronze.orders") in writer_edges, writer_edges
    assert ("bronze.orders", "silver.orders_clean") in silver_edges, silver_edges
    assert (
        "silver.orders_clean",
        "gold.orders_daily_metrics",
    ) in gold_edges, gold_edges

    # Connectivity is the property, not the three edges individually: the
    # output of each hop must be the input of the next, or the "path" is three
    # unrelated facts.
    reachable = {"streaming/orders_raw"}
    for source, target in list(writer_edges) + list(silver_edges) + list(gold_edges):
        if source in reachable:
            reachable.add(target)
    assert "gold.orders_daily_metrics" in reachable, (
        "no connected path from the landing prefix to Gold; edges are "
        f"{sorted(writer_edges | silver_edges | gold_edges)}"
    )


def test_each_output_dataset_is_claimed_by_exactly_one_job(emitted_events):
    """Duplicate producers are the defect the ownership registry prevents.

    Asserted against real emissions as well as at registration, because a
    second producer could be a service the registry never saw.
    """
    owners: dict[str, set[str]] = {}
    for event in emitted_events:
        for target in event.get("outputs") or []:
            key = f"{target['namespace']}/{target['name']}"
            owners.setdefault(key, set()).add(event["job"]["name"])

    contested = {ds: jobs for ds, jobs in owners.items() if len(jobs) > 1}
    assert not contested, f"datasets claimed by more than one job: {contested}"


def test_no_job_claims_a_kafka_edge_it_did_not_perform(emitted_events):
    """The honest gap, asserted as a gap.

    Bronze rows carry `kafka_offset`, so this edge is derivable in the writer.
    Emitting it would misattribute Spark's work, so nothing may claim a Kafka
    input until a boundary genuinely reads Kafka and says so.
    """
    for event in emitted_events:
        for source in event.get("inputs") or []:
            assert not source["namespace"].startswith("kafka://"), (
                f"{event['job']['name']} claims a Kafka input "
                f"({source['namespace']}/{source['name']}), but no first-party "
                "boundary reads Kafka. See docs/LINEAGE.md."
            )


def test_events_carry_run_identifiers_the_execution_really_had(emitted_events):
    """Static topology renders identically to real lineage; identifiers are
    what distinguish them."""
    writer_events = [e for e in emitted_events if e["job"]["name"] == WRITER_JOB]
    assert writer_events, "no writer events"

    for event in writer_events:
        facet = event["run"]["facets"]["provenance"]
        assert facet["identifiers"]["load_id"], event
        # Absences are declared, not omitted, and carry a reason.
        assert facet["absent"]["airflow.dag_run_id"]
        assert facet["absent"]["trace_id"]
        assert "airflow.dag_run_id" not in facet["identifiers"]

    silver_events = [e for e in emitted_events if e["job"]["name"] == SILVER_JOB]
    assert silver_events, "no bronze-to-silver events"
    for event in silver_events:
        assert event["run"]["facets"]["provenance"]["identifiers"]["cycle_id"]

    # Distinct runs must have distinct run ids, or every execution collapses
    # into one lineage run and the graph stops describing runs at all.
    load_ids = {
        e["run"]["facets"]["provenance"]["identifiers"]["load_id"]
        for e in writer_events
    }
    run_ids = {e["run"]["runId"] for e in writer_events}
    assert len(run_ids) == len(
        load_ids
    ), f"{len(load_ids)} distinct loads produced {len(run_ids)} run ids"


def test_the_receipt_is_written_out(emitted_events):
    """The artefact a reader can inspect after the stack is gone."""
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = RECEIPT_DIR / "runtime-lineage-graph.json"

    edges = sorted(
        {
            (event["job"]["name"], source["name"], target["name"])
            for event in emitted_events
            for source in event.get("inputs") or []
            for target in event.get("outputs") or []
        }
    )
    receipt.write_text(
        json.dumps(
            {
                "produced_by": "tests/integration/test_lineage_receipt.py",
                "event_count": len(emitted_events),
                "jobs": sorted({e["job"]["name"] for e in emitted_events}),
                "edges": [
                    {"job": job, "input": source, "output": target}
                    for job, source, target in edges
                ],
                "not_emitted": {
                    "kafka -> landing": (
                        "no OpenLineage Spark build for 4.2.0; see docs/LINEAGE.md"
                    )
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    written = json.loads(receipt.read_text(encoding="utf-8"))
    assert written["edges"], written
