"""Narrow OpenMetadata compatibility materialization for object-store inputs.

OpenMetadata's OpenLineage connector handles the Iceberg table side of the
writer event but, on the pinned 1.13.3 image, does not materialize an S3
LOCATION-only dataset.  This module supplements that one representation gap;
the Kafka OpenLineage event remains the runtime authority.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

API = os.getenv("METADATA_API", "http://metadata-server:8585/api").rstrip("/")
LINEAGE_TOPIC = os.getenv("METADATA_LINEAGE_TOPIC", "de-practicum-lineage")
ADAPTER_GROUP = os.getenv(
    "METADATA_OBJECT_STORE_ADAPTER_GROUP", "openmetadata-object-store-adapter"
)
STORAGE_SERVICE = os.getenv("METADATA_OBJECT_STORE_SERVICE", "landing_object_store")
STORAGE_SERVICE_TYPE = "CustomStorage"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class ObjectStoreDataset:
    bucket: str
    prefix: str

    @property
    def full_path(self) -> str:
        return f"s3://{self.bucket}/{self.prefix}"

    @property
    def child_name(self) -> str:
        return canonical_container_name(self.prefix)


def canonical_container_name(prefix: str) -> str:
    """Encode a prefix without collisions between slash/underscore spellings."""

    encoded: list[str] = []
    for char in prefix.strip("/"):
        if char.isalnum() or char in ".-":
            encoded.append(char)
        elif char == "_":
            encoded.append("__")
        else:
            encoded.append(f"_x{ord(char):x}_")
    return "p_" + "".join(encoded)


def object_store_dataset(dataset: dict[str, Any]) -> ObjectStoreDataset | None:
    """Parse only the normalized object-store DatasetRef shape.

    OpenLineage's NG-0.1 identity normalization makes s3/s3a/s3n equivalent;
    the adapter accepts those spellings and canonicalizes them to s3.  Kafka,
    Iceberg, malformed, and empty datasets are deliberately ignored.
    """

    namespace = str(dataset.get("namespace", "")).strip().lower()
    name = str(dataset.get("name", "")).strip("/")
    if not namespace.startswith(("s3://", "s3a://", "s3n://")):
        return None
    bucket = namespace.split("://", 1)[1].strip("/")
    if not bucket or not name or "/" in bucket or not _SAFE_NAME.sub("", name):
        return None
    return ObjectStoreDataset(bucket=bucket, prefix=name)


class MetadataAPI:
    def __init__(self, jwt: str):
        self.headers = {
            "Authorization": f"Bearer {jwt}",
            "Content-Type": "application/json",
        }

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any | None]:
        request = Request(
            f"{API}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers=self.headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except HTTPError as error:
            if error.code == 404:
                return 404, None
            raise

    def get_by_name(self, kind: str, fqn: str) -> Any | None:
        path = f"/v1/{kind}/name/{quote(fqn, safe='')}"
        status, payload = self.request("GET", path)
        if status == 200:
            return payload
        # A previous probe or interrupted run may have soft-deleted the exact
        # deterministic entity.  Include it so the caller can restore/reuse it
        # instead of creating a colliding duplicate.
        status, payload = self.request("GET", f"{path}?include=all")
        return payload if status == 200 else None

    def restore(self, kind: str, entity_id: str) -> Any:
        if kind == "containers":
            path = "/v1/containers/restore"
        elif kind == "services/storageServices":
            path = "/v1/services/storageServices/restore"
        else:
            raise ValueError(f"unsupported restore kind: {kind}")
        status, payload = self.request("PUT", path, {"id": entity_id})
        if status != 200:
            raise RuntimeError(f"{kind} restore failed: {status}")
        return payload


def _active_or_restore(api: MetadataAPI, kind: str, entity: Any | None) -> Any | None:
    if entity is not None and entity.get("deleted"):
        return api.restore(kind, entity["id"])
    return entity


def ensure_container(api: MetadataAPI, dataset: ObjectStoreDataset) -> str:
    """Create/reuse a bucket and deterministic prefix Container hierarchy."""

    service = _active_or_restore(
        api,
        "services/storageServices",
        api.get_by_name("services/storageServices", STORAGE_SERVICE),
    )
    if service is None:
        status, service = api.request(
            "PUT",
            "/v1/services/storageServices",
            {
                "name": STORAGE_SERVICE,
                "displayName": "Landing Object Store",
                "serviceType": STORAGE_SERVICE_TYPE,
                "description": (
                    "Compatibility representation for actual OpenLineage "
                    "object-store DatasetRefs; no cloud crawler."
                ),
                "connection": {"config": {"type": STORAGE_SERVICE_TYPE}},
            },
        )
        if status not in (200, 201):
            raise RuntimeError(f"storage service creation failed: {status}")

    bucket_fqn = f"{STORAGE_SERVICE}.{dataset.bucket}"
    bucket = _active_or_restore(
        api, "containers", api.get_by_name("containers", bucket_fqn)
    )
    if bucket is None:
        status, bucket = api.request(
            "POST",
            "/v1/containers",
            {
                "name": dataset.bucket,
                "displayName": f"{dataset.bucket} bucket",
                "service": STORAGE_SERVICE,
                "description": "Bucket derived from an actual OpenLineage DatasetRef.",
                "prefix": "/",
                "fullPath": f"s3://{dataset.bucket}",
                "fileFormats": ["parquet"],
            },
        )
        if status not in (200, 201):
            raise RuntimeError(f"bucket container creation failed: {status}")

    child_fqn = f"{bucket_fqn}.{dataset.child_name}"
    child = _active_or_restore(
        api, "containers", api.get_by_name("containers", child_fqn)
    )
    if child is None:
        status, child = api.request(
            "POST",
            "/v1/containers",
            {
                "name": dataset.child_name,
                "displayName": dataset.prefix,
                "service": STORAGE_SERVICE,
                "parent": {"id": bucket["id"], "type": "container"},
                "description": (
                    "Exact landing prefix derived from an actual OpenLineage "
                    "DatasetRef."
                ),
                "prefix": f"/{dataset.prefix}",
                "fullPath": dataset.full_path,
                "fileFormats": ["parquet"],
            },
        )
        if status not in (200, 201):
            raise RuntimeError(f"prefix container creation failed: {status}")
    return child["id"]


def native_edge_exists(api: MetadataAPI, container_id: str, table_fqn: str) -> bool:
    table = api.get_by_name("tables", table_fqn)
    if table is None:
        return False
    status, graph = api.request(
        "GET",
        f"/v1/lineage/table/name/{quote(table_fqn, safe='')}",
    )
    if status != 200:
        return False
    return any(
        edge.get("fromEntity") == container_id
        for edge in graph.get("upstreamEdges", [])
    )


def materialize_edge(
    api: MetadataAPI,
    *,
    container_id: str,
    table: dict[str, Any],
    event: dict[str, Any],
) -> bool:
    table_fqn = table["fullyQualifiedName"]
    if native_edge_exists(api, container_id, table_fqn):
        return False
    status, _ = api.request(
        "PUT",
        "/v1/lineage",
        {
            "edge": {
                "fromEntity": {"id": container_id, "type": "container"},
                "toEntity": {"id": table["id"], "type": "table"},
                "lineageDetails": {
                    "source": "OpenLineage",
                    "description": (
                        "OpenLineage-derived compatibility representation; "
                        f"job={event.get('job', {}).get('name')}; "
                        f"runId={event.get('run', {}).get('runId')}; "
                        f"input={event.get('inputs', [{}])[0].get('namespace')}/"
                        f"{event.get('inputs', [{}])[0].get('name')}"
                    ),
                },
            },
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"lineage compatibility edge failed: {status}")
    return True


def _table_fqn(dataset: dict[str, Any]) -> str | None:
    namespace = str(dataset.get("namespace", ""))
    name = str(dataset.get("name", ""))
    if namespace == "iceberg://iceberg-rest" and name:
        return f"lakehouse_trino.iceberg.{name}"
    return None


def materialize_from_event(api: MetadataAPI, event: dict[str, Any]) -> bool:
    if event.get("eventType") != "COMPLETE":
        return False
    inputs = event.get("inputs") or []
    outputs = event.get("outputs") or []
    if len(inputs) != 1 or len(outputs) != 1:
        return False
    dataset = object_store_dataset(inputs[0])
    table_fqn = _table_fqn(outputs[0])
    if dataset is None or table_fqn is None:
        return False
    table = api.get_by_name("tables", table_fqn)
    if table is None:
        return False
    container_id = ensure_container(api, dataset)
    return materialize_edge(api, container_id=container_id, table=table, event=event)


def run(jwt: str) -> int:
    """Consume actual events and supplement only unsupported object-store inputs."""

    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv("METADATA_LINEAGE_BROKERS", "kafka:9092"),
            "group.id": ADAPTER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([LINEAGE_TOPIC])
    api = MetadataAPI(jwt)
    materialized = 0
    idle = 0
    try:
        while idle < 5:
            message = consumer.poll(1.0)
            if message is None:
                idle += 1
                continue
            if message.error():
                idle += 1
                continue
            idle = 0
            try:
                if materialize_from_event(api, json.loads(message.value())):
                    materialized += 1
            except (KeyError, TypeError, ValueError) as error:
                print(f"Object-store adapter skipped malformed event: {error}")
    finally:
        consumer.close()
    print(f"Object-store compatibility adapter materialized {materialized} edge(s)")
    return materialized
