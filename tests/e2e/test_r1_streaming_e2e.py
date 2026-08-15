"""Live R1 closure checks for malformed-event ownership and reconciliation."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from tests.e2e.test_lakehouse_e2e import (
    BUCKET,
    Probe,
    _catalog,
    _docker_logs,
    _ensure_e2e_database,
    _fs,
    _pending_empty,
    _preflight,
    _save_docker_logs,
    _start_writer,
    assert_container_running,
    dead_letter_table,
    docker,
    docker_rm,
    kafka_create_topic,
    kafka_publish,
    landing_source_metadata,
    landing_rows,
    reconciliation_table,
    start_streaming,
    table_rows,
    wait_until,
)


KAFKA_CONTAINER = "de-demo-kafka"


def _delete_kafka_records(topic: str, offset: int) -> None:
    payload = json.dumps(
        {
            "version": 1,
            "partitions": [{"topic": topic, "partition": 0, "offset": offset}],
        }
    )
    command = (
        "cat > /tmp/r1-delete-records.json && "
        "/opt/kafka/bin/kafka-delete-records.sh "
        "--bootstrap-server localhost:9092 "
        "--offset-json-file /tmp/r1-delete-records.json"
    )
    proc = subprocess.run(
        ["docker", "exec", "-i", KAFKA_CONTAINER, "sh", "-lc", command],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kafka-delete-records failed: {proc.stderr.strip()}")


def _set_short_kafka_retention(topic: str) -> None:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            KAFKA_CONTAINER,
            "/opt/kafka/bin/kafka-configs.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--alter",
            "--entity-type",
            "topics",
            "--entity-name",
            topic,
            "--add-config",
            "retention.ms=1000,segment.ms=1000",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kafka-configs failed: {proc.stderr.strip()}")


def _kafka_earliest_offset(topic: str) -> int:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            KAFKA_CONTAINER,
            "/opt/kafka/bin/kafka-get-offsets.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--topic",
            topic,
            "--time",
            "-2",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return -1
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return int(lines[0].rsplit(":", 1)[-1]) if lines else -1


@pytest.mark.e2e
def test_r1_malformed_event_dead_letter_reconciliation_and_replay() -> None:
    _preflight()
    _ensure_e2e_database()

    run_id = f"r1{uuid.uuid4().hex[:8]}"
    topic = f"orders_{run_id}"
    namespace = f"e2e_{run_id}"
    tmpdir = Path(tempfile.mkdtemp(prefix="r1-e2e-"))
    state_file = tmpdir / "ingested.json"
    writer_log = tmpdir / "writer.log"
    stream_name: str | None = None
    writer = None

    valid = {
        "order_id": f"r1-valid-{run_id}",
        "customer": "r1",
        "amount": 10.0,
        "country": "UK",
        "status": "paid",
        "event_time": "2026-08-08T12:00:00+00:00",
        "business_version": 1,
    }
    try:
        kafka_create_topic(topic)
        kafka_publish(topic, [valid, "{not-json"])

        stream_name = start_streaming(run_id, topic)

        def landing_ready() -> bool:
            assert_container_running(stream_name)
            try:
                return landing_rows(_fs(), run_id) == 1
            except FileNotFoundError:
                return False

        wait_until(
            landing_ready,
            300,
            "R1 valid landing row",
            proc=None,
            logs=(lambda: _docker_logs(stream_name),),
        )

        def dispositions_ready() -> bool:
            try:
                dead = dead_letter_table(_fs(), run_id)
                reconciliation = reconciliation_table(_fs(), run_id)
            except FileNotFoundError:
                return False
            return (
                dead.num_rows == 1
                and reconciliation.num_rows >= 1
                and sum(reconciliation["observed_count"].to_pylist()) == 2
                and sum(reconciliation["valid_count"].to_pylist()) == 1
                and sum(reconciliation["dead_letter_count"].to_pylist()) == 1
            )

        wait_until(
            dispositions_ready,
            180,
            "R1 DLQ/reconciliation evidence",
            logs=(lambda: _docker_logs(stream_name),),
        )
        dead = dead_letter_table(_fs(), run_id)
        raw_metadata = landing_source_metadata(_fs(), run_id)
        assert dead["raw_payload"].to_pylist() == ["{not-json"]
        assert dead["dead_letter_reason"].to_pylist() in [
            ["invalid_json_or_schema"],
            ["missing_order_id"],
        ]
        assert dead["kafka_partition"].to_pylist() == [0]
        assert dead["kafka_offset"].to_pylist() == [1]
        assert dead["kafka_timestamp"].to_pylist()[0] is not None
        assert raw_metadata["kafka_partition"].to_pylist() == [0]
        assert raw_metadata["kafka_offset"].to_pylist() == [0]
        reconciliation = reconciliation_table(_fs(), run_id)
        assert reconciliation["min_kafka_partition"].to_pylist() == [0]
        assert reconciliation["max_kafka_partition"].to_pylist() == [0]
        assert reconciliation["min_kafka_offset"].to_pylist() == [0]
        assert reconciliation["max_kafka_offset"].to_pylist() == [1]

        docker_rm(stream_name)
        stream_name = None

        # Restarting with the same checkpoints and no new Kafka input must not
        # create another DLQ record or reconciliation disposition.
        stream_name = start_streaming(run_id, topic)
        time.sleep(20)
        assert dead_letter_table(_fs(), run_id).num_rows == 1
        reconciliation = reconciliation_table(_fs(), run_id)
        assert sum(reconciliation["observed_count"].to_pylist()) == 2
        docker_rm(stream_name)
        stream_name = None

        writer = _start_writer(run_id, state_file, writer_log)
        bronze_id = f"{namespace}.orders"
        bronze_probe = Probe(lambda: table_rows(_catalog(), bronze_id))
        wait_until(
            lambda: bronze_probe() == 1 and _pending_empty(state_file),
            180,
            "R1 valid row reaches Bronze",
            proc=writer,
            probes=(bronze_probe,),
            logs=(writer_log,),
        )
    finally:
        if writer is not None:
            writer.terminate()
            writer.wait(timeout=30)
        if stream_name:
            try:
                _save_docker_logs(stream_name, tmpdir / "streaming.log")
            finally:
                docker_rm(stream_name)
        catalog = _catalog()
        try:
            catalog.drop_table(f"{namespace}.orders")
        except Exception:
            pass
        try:
            catalog.drop_namespace(namespace)
        except Exception:
            pass
        try:
            _fs().delete_dir(f"{BUCKET}/e2e/{run_id}")
        except Exception:
            pass
        try:
            docker(
                "exec",
                "-i",
                KAFKA_CONTAINER,
                "/opt/kafka/bin/kafka-topics.sh",
                "--bootstrap-server",
                "localhost:9092",
                "--delete",
                "--topic",
                topic,
            )
        except RuntimeError:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.e2e
def test_r1_offset_loss_fails_loudly() -> None:
    """A committed checkpoint must not silently skip deleted Kafka records."""

    _preflight()
    run_id = f"r1loss{uuid.uuid4().hex[:8]}"
    topic = f"orders_{run_id}"
    stream_name: str | None = None
    try:
        kafka_create_topic(topic)
        stream_name = start_streaming(
            run_id,
            topic,
            max_offsets_per_trigger=1,
        )
        time.sleep(20)
        docker_rm(stream_name)
        stream_name = None

        kafka_publish(
            topic,
            [
                {
                    "order_id": f"r1-loss-{run_id}",
                    "event_time": "2026-08-08T12:00:00+00:00",
                    "business_version": 1,
                },
                {
                    "order_id": f"r1-loss-second-{run_id}",
                    "event_time": "2026-08-08T12:00:01+00:00",
                    "business_version": 1,
                },
            ],
        )
        stream_name = start_streaming(
            run_id,
            topic,
            max_offsets_per_trigger=1,
            trigger_seconds=60,
        )

        def one_landed() -> bool:
            try:
                return landing_rows(_fs(), run_id) == 1
            except FileNotFoundError:
                return False

        wait_until(
            one_landed,
            180,
            "one Kafka record committed before offset loss",
        )
        docker_rm(stream_name)
        stream_name = None
        _set_short_kafka_retention(topic)
        _delete_kafka_records(topic, 2)
        wait_until(
            lambda: _kafka_earliest_offset(topic) >= 2,
            120,
            "Kafka record becomes unavailable",
        )
        stream_name = start_streaming(
            run_id,
            topic,
            max_offsets_per_trigger=1,
            trigger_seconds=60,
        )

        def failed() -> bool:
            state = docker(
                "inspect",
                stream_name,
                "--format",
                "{{.State.Status}}|{{.State.ExitCode}}",
            ).strip()
            return state.startswith("exited|") and not state.endswith("|0")

        wait_until(
            failed,
            180,
            "Spark query fails on Kafka offset loss",
            logs=(lambda: docker("logs", stream_name),),
        )
        logs = docker("logs", stream_name)
        assert "offset" in logs.lower() or "data loss" in logs.lower()
    finally:
        if stream_name:
            try:
                docker_rm(stream_name)
            except RuntimeError:
                pass
        try:
            docker(
                "exec",
                "-i",
                KAFKA_CONTAINER,
                "/opt/kafka/bin/kafka-topics.sh",
                "--bootstrap-server",
                "localhost:9092",
                "--delete",
                "--topic",
                topic,
            )
        except RuntimeError:
            pass
