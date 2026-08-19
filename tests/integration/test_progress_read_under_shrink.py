"""A read that spans a shrinking overwrite must not return bytes never written.

Established in CI on 2026-08-19 and captured byte for byte: a 236-byte progress
document came back as 521 bytes, the last 285 of which were uninitialised
process memory - heap pointers, a stray `minio` literal, runs of zeros. A second
read and a sequential read of the same object both returned the intact 236
bytes with an identical digest, so the stored object was never corrupt.

The mechanism is the object's own shrink. Reserving work stores full object
paths under `work[load_id]`; completing it replaces them with a compact
`completed` entry and prunes. A random-access handle takes the object's length
from a HEAD at open and applies it to a body fetched later, so a read issued
across that overwrite is sized by the larger predecessor and served the smaller
successor - and PyArrow hands back the whole over-sized buffer.

These tests force the ordering the race had to hit by luck, and assert what the
medallion's own reader must do under it. They fail against the pre-fix
`_read_json`, which used `open_input_file`.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from medallion import iceberg_medallion as m
from tests.integration.test_m4_gold_cutover import BUCKET, storage

pytestmark = pytest.mark.integration

# Sized to bracket what CI observed: the large document comfortably exceeds the
# 236-byte boundary, the small one is comfortably under it.
LARGE = json.dumps(
    {
        "version": 1,
        "next_sequence": 1,
        "work": {
            "001-seed": {
                "status": "in_flight",
                "source_paths": [f"de-practicum/m4/{'x' * 60}/outbox/001-seed.json"],
                "bronze_data_files": [
                    f"de-practicum/m4/{'y' * 60}/data/part-0.parquet"
                ],
            }
        },
        "completed": {},
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")

SMALL = json.dumps(
    {
        "version": 1,
        "next_sequence": 2,
        "work": {},
        "completed": {"001-seed": {"sequence": 1, "changed_keys": ["a"]}},
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")


def _write(filesystem, path: str, payload: bytes) -> None:
    with filesystem.open_output_stream(path) as output:
        output.write(payload)


@pytest.fixture()
def shrinking_object():
    filesystem = storage()
    path = f"{BUCKET}/diagnostics/{uuid.uuid4().hex}/progress.json"
    _write(filesystem, path, LARGE)
    yield filesystem, path
    try:
        filesystem.delete_file(path)
    except OSError:
        pass


def test_the_two_payloads_bracket_the_observed_failure_offset():
    """Guards the experiment itself: a shrink that is not a shrink proves nothing."""

    assert len(LARGE) > 260, len(LARGE)
    assert len(SMALL) < 236, len(SMALL)


def test_the_medallion_reader_survives_a_shrink_between_head_and_body(
    shrinking_object,
):
    """The regression contract. Fails against a random-access `_read_json`.

    The size is observed while the object is still large, the object is then
    replaced by a smaller one, and only then is the read issued - the ordering a
    random-access handle turns into an over-sized buffer.
    """

    filesystem, path = shrinking_object
    assert filesystem.get_file_info(path).size == len(LARGE)

    _write(filesystem, path, SMALL)

    document = m._read_json(filesystem, path)

    assert document == json.loads(SMALL.decode("utf-8"))
    assert document["work"] == {}


def test_the_medallion_reader_returns_the_object_and_nothing_else(shrinking_object):
    """No trailing bytes, whichever version is served.

    Reads the object repeatedly across a shrink. Every result must be one of the
    two documents exactly - never one of them followed by anything.
    """

    filesystem, path = shrinking_object

    seen = []
    for _ in range(3):
        seen.append(m._read_json(filesystem, path))
        _write(filesystem, path, SMALL if len(seen) % 2 else LARGE)

    for document in seen:
        assert document in (
            json.loads(LARGE.decode("utf-8")),
            json.loads(SMALL.decode("utf-8")),
        ), document


def test_the_writer_commit_log_reader_is_sequential_too():
    """The writer read the same way, so it carried the same defect.

    Asserted on the source rather than on a live Spark log: the defect is which
    API is called, and calling it correctly is the whole fix.
    """

    source = (
        Path(__file__).resolve().parents[2] / "iceberg" / "writer" / "iceberg_writer.py"
    )
    text = source.read_text(encoding="utf-8")
    body = text.split("def _read_spark_commit_log", 1)[1].split("\ndef ", 1)[0]
    assert "open_input_stream" in body
    assert "open_input_file(" not in body
