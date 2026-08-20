"""Focused contracts for the object-store OpenMetadata compatibility adapter."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "openlineage_container_adapter",
    ROOT / "metadata/scripts/openlineage_container_adapter.py",
)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


def test_object_store_identity_normalizes_equivalent_s3_spellings() -> None:
    s3 = adapter.object_store_dataset(
        {"namespace": "s3://de-practicum", "name": "landing/orders_raw"}
    )
    s3a = adapter.object_store_dataset(
        {"namespace": "s3a://de-practicum", "name": "/landing/orders_raw/"}
    )

    assert s3 == s3a
    assert s3 is not None
    assert s3.full_path == "s3://de-practicum/landing/orders_raw"
    assert s3.child_name == "p_landing_x2f_orders__raw"
    assert adapter.canonical_container_name("a/b") != adapter.canonical_container_name(
        "a_b"
    )
    assert adapter.canonical_container_name("a/b") == adapter.canonical_container_name(
        "a/b"
    )


def test_object_store_identity_rejects_non_storage_and_malformed_inputs() -> None:
    assert (
        adapter.object_store_dataset({"namespace": "kafka://kafka", "name": "orders"})
        is None
    )
    assert (
        adapter.object_store_dataset(
            {"namespace": "iceberg://iceberg-rest", "name": "bronze.orders"}
        )
        is None
    )
    assert (
        adapter.object_store_dataset({"namespace": "s3://", "name": "orders"}) is None
    )
    assert (
        adapter.object_store_dataset({"namespace": "s3://bucket", "name": ""}) is None
    )


def test_output_mapping_is_only_for_existing_iceberg_namespace() -> None:
    assert (
        adapter._table_fqn(
            {"namespace": "iceberg://iceberg-rest", "name": "bronze.orders"}
        )
        == "lakehouse_trino.iceberg.bronze.orders"
    )
    assert (
        adapter._table_fqn(
            {"namespace": "s3://de-practicum", "name": "landing/orders_raw"}
        )
        is None
    )


def test_native_edge_guard_prevents_duplicate_materialization() -> None:
    class FakeAPI:
        def __init__(self):
            self.calls = []

        def get_by_name(self, kind, fqn):
            self.calls.append(("get", kind, fqn))
            return {"id": "bronze-id", "fullyQualifiedName": fqn}

        def request(self, method, path, body=None):
            self.calls.append((method, path, body))
            return 200, {"upstreamEdges": [{"fromEntity": "container-id"}]}

    fake = FakeAPI()
    assert adapter.native_edge_exists(fake, "container-id", "target.fqn") is True
    assert not any(call[0] == "PUT" for call in fake.calls)


def test_new_edge_preserves_openlineage_correlation() -> None:
    class FakeAPI:
        def __init__(self):
            self.calls = []

        def get_by_name(self, kind, fqn):
            self.calls.append(("get", kind, fqn))
            return {"id": "table-id", "fullyQualifiedName": fqn}

        def request(self, method, path, body=None):
            self.calls.append((method, path, body))
            if path.startswith("/v1/lineage/table/name/"):
                return 200, {"upstreamEdges": []}
            return 200, None

    fake = FakeAPI()
    event = {
        "job": {"name": "iceberg-writer.landing-to-bronze"},
        "run": {"runId": "run-123"},
        "inputs": [{"namespace": "s3://bucket", "name": "landing/orders_raw"}],
    }
    assert adapter.materialize_edge(
        fake,
        container_id="container-id",
        table={"id": "table-id", "fullyQualifiedName": "target.fqn"},
        event=event,
    )
    put = next(call for call in fake.calls if call[0] == "PUT")
    details = put[2]["edge"]["lineageDetails"]
    assert details["source"] == "OpenLineage"
    assert "run-123" in details["description"]
    assert "s3://bucket/landing/orders_raw" in details["description"]
