"""SPIKE-1 / permanent compatibility guard for ADR-0001 decision D-3.

This is not a throwaway spike. It is the standing guard for the interop contract
a Trino-executed Silver projection would depend on::

    PyIceberg creates Silver
        -> Trino performs a conditional business-key MERGE
        -> Iceberg v2 data/delete files
        -> PyIceberg reads the resulting table correctly     <-- CURRENTLY BROKEN
        -> Gold rebuilds from persisted Silver
        -> maintenance runs
        -> both engines still read the same logical result

RESULT OF SPIKE-1 (revision d20b2062, Trino 483, PyIceberg 0.11.1):

* The conditional MERGE itself works exactly as ADR-0001 D-1/D-1a requires.
  Monotonic ``business_version`` semantics hold, including across partitions.
* **PyIceberg cannot read a table Trino has written with position deletes.**
  PyArrow raises ``Not yet implemented: DecodeArrow of DictAccumulator for
  DeltaLengthByteArrayDecoder`` when reading Trino's delete files. Reproduced on
  BOTH pyarrow 21.0.0 (requirements-dev pin) and pyarrow 25.0.0 (what the
  iceberg image actually installs).
* ``write.merge.mode = copy-on-write`` is accepted and stored, and then ignored:
  Trino writes position deletes anyway.
* ``optimize`` compacts the deletes away and restores PyIceberg reads - the only
  known repair, and an expensive one (see the test below).

D-3 therefore FAILED the go/no-go and returned to the design space. These tests
stay so that a future Trino, PyIceberg or PyArrow upgrade is measured against the
same contract instead of being assumed. ``test_pyiceberg_reads_trino_position_deletes``
is ``xfail(strict=True)``: **when it starts passing, D-3 should be reconsidered.**

See ``docs/adr/0001-incremental-silver-and-gold.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import date, datetime

import pyarrow as pa
import pytest
from pyiceberg.catalog.rest import RestCatalog
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform
from pyiceberg.types import (
    DateType,
    DoubleType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

ICEBERG_CATALOG_URI = os.getenv("ICEBERG_CATALOG_URI", "http://localhost:18181")
ICEBERG_WAREHOUSE = os.getenv("ICEBERG_WAREHOUSE", "s3://de-practicum/warehouse")
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localhost:19000")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "minio")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minio123")
TRINO_CONTAINER = os.getenv("TRINO_CONTAINER", "de-demo-trino")

# Silver as ADR-0001 D-1a proposes it: business columns plus business_version.
SILVER_V2_SCHEMA = Schema(
    NestedField(1, "order_id", StringType(), required=False),
    NestedField(2, "customer", StringType(), required=False),
    NestedField(3, "amount", DoubleType(), required=False),
    NestedField(4, "status", StringType(), required=False),
    NestedField(5, "event_time", TimestampType(), required=False),
    NestedField(6, "event_date", DateType(), required=False),
    NestedField(7, "business_version", LongType(), required=False),
)

SILVER_PARTITION_SPEC = PartitionSpec(
    PartitionField(
        source_id=6, field_id=1000, transform=DayTransform(), name="event_date_day"
    )
)

COLS = [
    "order_id",
    "customer",
    "amount",
    "status",
    "event_time",
    "event_date",
    "business_version",
]

# Iceberg manifest content codes: 0 = data file, 1 = position deletes.
CONTENT_DATA = "0"
CONTENT_POSITION_DELETES = "1"


# --------------------------------------------------------------------------- #
# Infrastructure
# --------------------------------------------------------------------------- #
def catalog() -> RestCatalog:
    return RestCatalog(
        "default",
        **{
            "uri": ICEBERG_CATALOG_URI,
            "warehouse": ICEBERG_WAREHOUSE,
            "s3.endpoint": S3_ENDPOINT,
            "s3.access-key-id": ACCESS_KEY,
            "s3.secret-access-key": SECRET_KEY,
            "s3.region": "us-east-1",
            "s3.path-style-access": "true",
        },
    )


def trino_raw(sql: str) -> str:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            TRINO_CONTAINER,
            "trino",
            "--catalog",
            "iceberg",
            "--execute",
            sql,
            "--output-format",
            "CSV_HEADER",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"trino failed: {proc.stderr.strip()[:400]} | sql: {sql}")
    return proc.stdout


def trino_rows(sql: str) -> list[list[str]]:
    lines = [line for line in trino_raw(sql).splitlines() if line.strip()]
    return [[c.strip().strip('"') for c in line.split(",")] for line in lines[1:]]


def trino_exec(sql: str) -> None:
    trino_raw(sql)


# --------------------------------------------------------------------------- #
# Fixtures and data
# --------------------------------------------------------------------------- #
@pytest.fixture
def lake():
    ns = f"spike_{uuid.uuid4().hex[:8]}"
    cat = catalog()
    cat.create_namespace_if_not_exists(ns)
    cat.create_table(
        f"{ns}.silver", schema=SILVER_V2_SCHEMA, partition_spec=SILVER_PARTITION_SPEC
    )
    cat.create_table(
        f"{ns}.staging", schema=SILVER_V2_SCHEMA, partition_spec=PartitionSpec()
    )
    yield ns
    try:
        trino_exec(f"DROP SCHEMA IF EXISTS iceberg.{ns} CASCADE")
    except Exception:
        pass
    for table in ("silver", "staging"):
        try:
            cat.drop_table(f"{ns}.{table}")
        except Exception:
            pass
    try:
        cat.drop_namespace(ns)
    except Exception:
        pass


def order_rows(items: list[dict]) -> pa.Table:
    return pa.table(
        {
            "order_id": pa.array([i["order_id"] for i in items], type=pa.string()),
            "customer": pa.array(
                [i.get("customer", "cust") for i in items], type=pa.string()
            ),
            "amount": pa.array([i["amount"] for i in items], type=pa.float64()),
            "status": pa.array([i["status"] for i in items], type=pa.string()),
            "event_time": pa.array(
                [datetime(2026, 8, i.get("day", 8), 12) for i in items],
                type=pa.timestamp("us"),
            ),
            "event_date": pa.array(
                [date(2026, 8, i.get("day", 8)) for i in items], type=pa.date32()
            ),
            "business_version": pa.array(
                [i["version"] for i in items], type=pa.int64()
            ),
        }
    )


def stage(ns: str, items: list[dict]) -> None:
    catalog().load_table(f"{ns}.staging").overwrite(order_rows(items))


def merge(ns: str) -> None:
    """The conditional business-key MERGE that D-3 would depend on."""
    set_clause = ", ".join(f"{c} = s.{c}" for c in COLS if c != "order_id")
    trino_exec(
        f"MERGE INTO iceberg.{ns}.silver t USING iceberg.{ns}.staging s "
        f"ON t.order_id = s.order_id "
        f"WHEN MATCHED AND s.business_version > t.business_version "
        f"THEN UPDATE SET {set_clause} "
        f"WHEN NOT MATCHED THEN INSERT ({', '.join(COLS)}) "
        f"VALUES ({', '.join('s.' + c for c in COLS)})"
    )


def trino_state(ns: str) -> dict[str, tuple[int, float, str]]:
    rows = trino_rows(
        f"SELECT order_id, business_version, amount, status "
        f"FROM iceberg.{ns}.silver ORDER BY order_id"
    )
    return {r[0]: (int(r[1]), float(r[2]), r[3]) for r in rows}


def file_mix(ns: str) -> dict[str, int]:
    rows = trino_rows(
        f'SELECT content, count(*) FROM iceberg.{ns}."silver$files" GROUP BY content'
    )
    return {r[0]: int(r[1]) for r in rows}


def pyiceberg_read(ns: str):
    return catalog().load_table(f"{ns}.silver").scan().to_arrow()


def evidence(ns: str, label: str) -> dict:
    tbl = catalog().load_table(f"{ns}.silver")
    ev = {
        "label": label,
        "snapshots": len(list(tbl.metadata.snapshots)),
        "files_by_content": file_mix(ns),
        "plan_files": len(list(tbl.scan().plan_files())),
    }
    print(f"EVIDENCE {json.dumps(ev)}", flush=True)
    return ev


# --------------------------------------------------------------------------- #
# THE GATE - this single test decides D-3
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
@pytest.mark.xfail(
    strict=True,
    reason=(
        "SPIKE-1: PyArrow cannot decode Trino's position-delete files "
        "(DeltaLengthByteArrayDecoder). Reproduced on pyarrow 21 and 25. "
        "IF THIS STARTS PASSING, revisit ADR-0001 D-3 - the interop blocker is gone."
    ),
)
def test_pyiceberg_reads_trino_position_deletes(lake):
    """The go/no-go for a Trino-owned Silver projection.

    Gold is rebuilt from persisted Silver through PyIceberg (ADR-0001 D-4), so
    PyIceberg MUST be able to read whatever Trino writes. It cannot.
    """
    ns = lake
    stage(ns, [{"order_id": "o-1", "version": 1, "amount": 10.0, "status": "created"}])
    merge(ns)
    stage(
        ns, [{"order_id": "o-1", "version": 5, "amount": 50.0, "status": "delivered"}]
    )
    merge(ns)

    assert file_mix(ns).get(CONTENT_POSITION_DELETES), "expected position deletes"

    arrow = pyiceberg_read(ns)
    assert arrow.num_rows == 1
    assert arrow.to_pylist()[0]["business_version"] == 5


# --------------------------------------------------------------------------- #
# What DOES work: the MERGE semantics themselves, verified through Trino
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_late_lower_version_never_regresses_silver(lake):
    """v1 -> v5 -> late v3: Silver stays at v5. (ADR-0001 FF-04)"""
    ns = lake

    stage(ns, [{"order_id": "o-1", "version": 1, "amount": 10.0, "status": "created"}])
    merge(ns)
    assert trino_state(ns) == {"o-1": (1, 10.0, "created")}

    stage(
        ns, [{"order_id": "o-1", "version": 5, "amount": 50.0, "status": "delivered"}]
    )
    merge(ns)
    assert trino_state(ns) == {"o-1": (5, 50.0, "delivered")}

    stage(ns, [{"order_id": "o-1", "version": 3, "amount": 30.0, "status": "shipped"}])
    merge(ns)
    assert trino_state(ns) == {"o-1": (5, 50.0, "delivered")}
    evidence(ns, "after-late-lower-version")


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_version_crossing_partition_boundary_keeps_one_row(lake):
    """v1 on day 8, v2 on day 9: exactly one row per order_id, globally.

    This is the scenario that eliminated ADR-0001 option C: a partition-scoped
    rebuild would leave the day-8 representation behind. A business-key MERGE
    does not. (ADR-0001 FF-09)
    """
    ns = lake

    stage(
        ns,
        [
            {
                "order_id": "o-x",
                "version": 1,
                "amount": 10.0,
                "status": "created",
                "day": 8,
            }
        ],
    )
    merge(ns)
    stage(
        ns,
        [{"order_id": "o-x", "version": 2, "amount": 20.0, "status": "paid", "day": 9}],
    )
    merge(ns)

    assert trino_state(ns) == {"o-x": (2, 20.0, "paid")}
    dates = trino_rows(
        f"SELECT DISTINCT event_date FROM iceberg.{ns}.silver WHERE order_id='o-x'"
    )
    assert (
        len(dates) == 1
    ), f"stale representation left behind in another partition: {dates}"
    evidence(ns, "after-cross-partition-update")


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_delta_must_be_collapsed_to_one_row_per_key(lake):
    """SPIKE-1 answer: pre-collapse of the delta is a HARD requirement.

    Two versions of one order in a single source batch make Trino abort with
    ``One MERGE target table row matched more than one source row``. This is a
    design constraint on whatever builds the delta, not a bug: the delta must be
    reduced to ``(order_id, max(business_version))`` before the MERGE runs.

    Asserted rather than merely observed, so that a change in Trino's behaviour
    is reported instead of silently relaxing a constraint the design relies on.
    """
    ns = lake
    stage(ns, [{"order_id": "o-2", "version": 1, "amount": 10.0, "status": "created"}])
    merge(ns)

    multi_version = [
        {"order_id": "o-2", "version": 3, "amount": 30.0, "status": "shipped"},
        {"order_id": "o-2", "version": 5, "amount": 50.0, "status": "delivered"},
    ]
    stage(ns, multi_version)
    with pytest.raises(RuntimeError, match="matched more than one source row"):
        merge(ns)

    # Silver is untouched by the aborted MERGE - the failure is atomic.
    assert trino_state(ns) == {"o-2": (1, 10.0, "created")}

    # The delta collapsed to one row per key merges cleanly.
    stage(ns, [max(multi_version, key=lambda r: r["version"])])
    merge(ns)
    assert trino_state(ns) == {"o-2": (5, 50.0, "delivered")}


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_same_version_different_payload_is_dropped_silently(lake):
    """Same (order_id, business_version), different payload. (ADR-0001 FF-14)

    The MERGE predicate is strictly greater-than, so an equal version cannot
    update Silver: the conflict is ignored rather than reported. This pins that
    behaviour and shows FF-14 must be enforced BEFORE the merge, when the delta
    is constructed.
    """
    ns = lake
    stage(ns, [{"order_id": "o-3", "version": 4, "amount": 40.0, "status": "paid"}])
    merge(ns)

    stage(
        ns, [{"order_id": "o-3", "version": 4, "amount": 99.0, "status": "cancelled"}]
    )
    merge(ns)
    assert trino_state(ns) == {
        "o-3": (4, 40.0, "paid")
    }, "equal version must not update"

    conflicts = trino_rows(
        f"SELECT s.order_id FROM iceberg.{ns}.staging s "
        f"JOIN iceberg.{ns}.silver t ON s.order_id = t.order_id "
        f"WHERE s.business_version = t.business_version "
        f"AND (s.amount != t.amount OR s.status != t.status)"
    )
    assert (
        conflicts
    ), "FF-14 must be a pre-merge check; the MERGE itself cannot surface this"


# --------------------------------------------------------------------------- #
# The only known repair, and what it costs
# --------------------------------------------------------------------------- #
@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_optimize_compacts_deletes_and_restores_pyiceberg_reads(lake):
    """`optimize` is the only escape found - and it is not a cheap one.

    Compaction removes the position deletes, after which PyIceberg reads again.
    But Silver is unreadable by PyIceberg between the MERGE and the compaction,
    so a Trino-owned projection would have to compact after EVERY cycle. That
    rewrites touched files each time, which removes the performance rationale
    for incremental processing and multiplies snapshot churn straight into F-301.
    """
    ns = lake
    stage(ns, [{"order_id": "o-1", "version": 1, "amount": 10.0, "status": "created"}])
    merge(ns)
    stage(
        ns, [{"order_id": "o-1", "version": 5, "amount": 50.0, "status": "delivered"}]
    )
    merge(ns)

    before = evidence(ns, "after-merge")
    assert before["files_by_content"].get(CONTENT_POSITION_DELETES) == 1

    with pytest.raises(Exception):
        pyiceberg_read(ns)

    trino_exec(
        f"ALTER TABLE iceberg.{ns}.silver EXECUTE optimize(file_size_threshold => '10MB')"
    )
    after = evidence(ns, "after-optimize")
    assert CONTENT_POSITION_DELETES not in after["files_by_content"]

    arrow = pyiceberg_read(ns)
    assert arrow.num_rows == 1
    assert arrow.to_pylist()[0]["business_version"] == 5
    assert trino_state(ns) == {"o-1": (5, 50.0, "delivered")}


@pytest.mark.integration
@pytest.mark.iceberg
@pytest.mark.trino
def test_copy_on_write_table_properties_are_accepted_then_ignored(lake):
    """Trino 483 stores write.merge.mode = copy-on-write and writes deletes anyway.

    Recorded because it is the obvious first workaround to reach for, and it
    does not work. If a future Trino honours it, this test fails and the
    interop blocker may be gone - check the xfail gate above at the same time.
    """
    ns = lake
    cat = catalog()
    cat.drop_table(f"{ns}.silver")
    cat.create_table(
        f"{ns}.silver",
        schema=SILVER_V2_SCHEMA,
        partition_spec=SILVER_PARTITION_SPEC,
        properties={
            "write.merge.mode": "copy-on-write",
            "write.update.mode": "copy-on-write",
            "write.delete.mode": "copy-on-write",
        },
    )

    props = {
        r[0]: r[1]
        for r in trino_rows(f'SELECT * FROM iceberg.{ns}."silver$properties"')
    }
    assert props.get("write.merge.mode") == "copy-on-write", "property must be stored"

    stage(ns, [{"order_id": "o-1", "version": 1, "amount": 10.0, "status": "created"}])
    merge(ns)
    stage(
        ns, [{"order_id": "o-1", "version": 5, "amount": 50.0, "status": "delivered"}]
    )
    merge(ns)

    assert file_mix(ns).get(CONTENT_POSITION_DELETES) == 1, (
        "Trino honoured copy-on-write - the SPIKE-1 blocker may be resolved; "
        "revisit ADR-0001 D-3"
    )
    assert trino_state(ns) == {"o-1": (5, 50.0, "delivered")}
