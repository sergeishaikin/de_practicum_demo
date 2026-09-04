"""NG-0.1's end-to-end receipt, produced from live state rather than asserted.

The item requires "at least one end-to-end receipt linking Kafka position →
processing identity → Iceberg snapshot". That chain is only real if each hop is
read back out of the platform:

    (kafka.topic, partition, offset)   a column on the Bronze row
              ↓
    load_id                            stamped into the append's snapshot summary
              ↓
    iceberg.snapshot_id                the snapshot carrying that stamp

The middle hop is the one that could rot silently. `kafka_offset` and
`snapshot_id` are both recorded today, but without `load-id` in the snapshot
summary they are two unrelated facts about the same append and the chain has a
hole exactly where the writer is.

Runs against the same live REST catalog and object store as the other
integration tests, and mutates only its own throwaway namespace.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest

from common import provenance as p
from medallion import iceberg_medallion as m
from tests.integration.test_m3_b2_recovery import append_work, catalog, fs

pytestmark = [pytest.mark.integration, pytest.mark.iceberg]

REPO_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_DIR = REPO_ROOT / "artifacts" / "provenance"
TOPIC = "orders"


def _row(order_id: str, partition: int, offset: int) -> dict:
    moment = datetime(2026, 1, 1, 12)
    return {
        "order_id": order_id,
        "customer": f"{order_id}-v1",
        "amount": 10.0,
        "country": "US",
        "status": "paid",
        "event_time": moment,
        "kafka_timestamp": moment,
        "kafka_partition": partition,
        "kafka_offset": offset,
        "event_date": date(2026, 1, 1),
        "business_version": 1,
    }


def test_a_kafka_position_is_traceable_to_the_iceberg_snapshot_that_holds_it():
    run = uuid.uuid4().hex[:8]
    namespace = f"prov_{run}"
    load_id = f"load-{run}"
    partition, offset = 0, 4242

    cat = catalog()
    storage = fs()
    cat.create_namespace_if_not_exists(namespace)
    cat.create_table(
        f"{namespace}.bronze",
        schema=m.SILVER_SCHEMA,
        partition_spec=m.SILVER_PARTITION_SPEC,
    )
    bronze = cat.load_table(f"{namespace}.bronze")

    try:
        append_work(
            bronze,
            load_id,
            [_row("a", partition, offset)],
            storage,
            f"prov/{run}/outbox",
        )

        bronze = cat.load_table(f"{namespace}.bronze")

        # Hop 1: the Kafka position, read back off the stored row.
        rows = bronze.scan().to_arrow().to_pylist()
        assert len(rows) == 1, rows
        stored = rows[0]
        assert stored["kafka_partition"] == partition
        assert stored["kafka_offset"] == offset

        # Hop 2 and 3: the snapshot that carries this load's stamp.
        stamped = [
            snapshot
            for snapshot in bronze.metadata.snapshots
            if (snapshot.summary or {}).get("load-id") == load_id
        ]
        assert len(stamped) == 1, (
            "exactly one snapshot must carry this load-id; without it the Kafka "
            f"position and the snapshot are unrelated facts. found: {stamped}"
        )
        snapshot = stamped[0]

        envelope = p.ProvenanceEnvelope(
            values={
                p.KAFKA_TOPIC: TOPIC,
                p.KAFKA_PARTITION: stored["kafka_partition"],
                p.KAFKA_OFFSET: stored["kafka_offset"],
                p.LOAD_ID: load_id,
                p.ICEBERG_TABLE: f"{namespace}.bronze",
                p.ICEBERG_SNAPSHOT_ID: snapshot.snapshot_id,
            },
            unknown={
                p.DAG_RUN_ID: "appended by the test harness, not by an Airflow run",
                p.TRACE_ID: "no tracing backend exists yet; NG-0.4 introduces one",
            },
        ).requires(
            p.KAFKA_TOPIC,
            p.KAFKA_PARTITION,
            p.KAFKA_OFFSET,
            p.LOAD_ID,
            p.ICEBERG_TABLE,
            p.ICEBERG_SNAPSHOT_ID,
        )

        # The envelope refused to invent the two identifiers this boundary does
        # not have, and said why - which is the half of NG-0.1 prose cannot hold.
        assert p.DAG_RUN_ID not in envelope.to_dict()
        assert p.TRACE_ID not in envelope.to_dict()

        RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
        receipt = RECEIPT_DIR / f"kafka-to-snapshot-{run}.json"
        receipt.write_text(
            json.dumps(
                {
                    "produced_by": "tests/integration/test_provenance_receipt.py",
                    "chain": ["kafka position", "load_id", "iceberg snapshot"],
                    "identifiers": envelope.to_dict(),
                    "absent": envelope.reasons(),
                    "code_revision": os.getenv("GITHUB_SHA", "not recorded locally"),
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

        assert (
            json.loads(receipt.read_text(encoding="utf-8"))["identifiers"][
                p.ICEBERG_SNAPSHOT_ID
            ]
            == snapshot.snapshot_id
        )
    finally:
        cat.drop_table(f"{namespace}.bronze")
        cat.drop_namespace(namespace)
