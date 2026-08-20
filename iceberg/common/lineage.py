"""Runtime lineage emission: what each boundary actually read and wrote.

NG-0.1 gave the platform a vocabulary for identity. This module makes the
*relationships* between the datasets those identifiers describe into a runtime
fact, emitted as OpenLineage events by the boundary that performed the work.

Three rules carry the weight, and each exists because of a specific way lineage
goes wrong.

**An edge belongs to the boundary that performed it.** The Iceberg writer holds
Bronze rows carrying Kafka offsets, so it *could* emit a Kafka-to-Bronze edge.
It never read Kafka - it read Parquet from a landing prefix - and a graph that
misattributes work is worse than one with a labelled hole, because the hole can
be closed while the false edge propagates into everything downstream.

**One output dataset has one owner.** Duplicate emitters produce contradictory
edges that no consumer can arbitrate. `register_edge_owner` makes that a startup
failure rather than a silently doubled graph.

**Emission never touches the data path.** Everywhere else this repository fails
closed; lineage deliberately inverts that, because a lineage backend outage must
not become a data outage. Every emit is wrapped and every failure is counted -
the counter being the part that separates a working emitter from one that has
been failing silently for a week.

Dataset identity comes from configuration, never from the runtime host: a
container id in a namespace would fork one table into a new alias on every
restart.
"""

from __future__ import annotations

import os
import sys
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import attr
from openlineage.client import OpenLineageClient
from openlineage.client.event_v2 import (
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)
from openlineage.client.facet_v2 import RunFacet

from common import provenance as prov

PRODUCER = "https://github.com/sergeishaikin/de_practicum_demo"

# The job namespace groups this platform's jobs. It is configuration, never a
# hostname, for the same reason dataset namespaces are.
JOB_NAMESPACE = os.getenv("OPENLINEAGE_NAMESPACE", "de-practicum")

LINEAGE_DISABLED = os.getenv("OPENLINEAGE_DISABLED", "").lower() in {
    "1",
    "true",
    "yes",
}


# --------------------------------------------------------------------------
# Dataset identity
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetRef:
    """A dataset's stable identity: the pair OpenLineage keys datasets by."""

    namespace: str
    name: str

    def as_input(self) -> InputDataset:
        return InputDataset(namespace=self.namespace, name=self.name)

    def as_output(self) -> OutputDataset:
        return OutputDataset(namespace=self.namespace, name=self.name)


def normalize_endpoint(endpoint: str) -> str:
    """Reduce the spellings of one endpoint to a single authority.

    ``http://iceberg-rest:8181``, ``iceberg-rest:8181/`` and ``iceberg-rest``
    are the same catalog. Left alone they would fork one table into three
    datasets, which is the alias problem NG-0.2 forbids. Credentials are
    dropped because an endpoint that carries them is a leak as well as an
    alias, and the port is dropped because one service reached on two ports is
    still one service.
    """
    raw = (endpoint or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"scheme://{raw}"
    return (urlparse(raw).hostname or "").lower()


def kafka_dataset(bootstrap: str, topic: str) -> DatasetRef:
    """A Kafka topic, namespaced by its bootstrap authority."""
    return DatasetRef(namespace=f"kafka://{normalize_endpoint(bootstrap)}", name=topic)


def object_store_dataset(bucket: str, prefix: str) -> DatasetRef:
    """A prefix in object storage.

    ``s3a://`` and ``s3://`` spellings of one bucket normalise together: the
    scheme records which client library was used, not which bucket was written.
    """
    return DatasetRef(
        namespace=f"s3://{_strip_scheme(bucket).strip('/').lower()}",
        name=prefix.strip("/"),
    )


def iceberg_dataset(catalog_uri: str, table_identifier: str) -> DatasetRef:
    """An Iceberg table, namespaced by the catalog that owns it."""
    return DatasetRef(
        namespace=f"iceberg://{normalize_endpoint(catalog_uri)}",
        name=table_identifier,
    )


def _strip_scheme(value: str) -> str:
    for scheme in ("s3a://", "s3n://", "s3://"):
        if value.lower().startswith(scheme):
            return value[len(scheme) :]
    return value


# --------------------------------------------------------------------------
# Edge ownership
# --------------------------------------------------------------------------


class DuplicateEdgeOwner(RuntimeError):
    """Two boundaries claimed one output dataset."""


_EDGE_OWNERS: dict[DatasetRef, str] = {}


def register_edge_owner(output: DatasetRef, owner: str) -> None:
    """Claim an output dataset for one boundary.

    Re-registering the same owner is idempotent, so a service that restarts its
    loop does not fight itself. A *different* owner is a design error and raises
    here rather than producing two contradictory versions of one edge.
    """
    existing = _EDGE_OWNERS.get(output)
    if existing is not None and existing != owner:
        raise DuplicateEdgeOwner(
            f"{output.namespace}/{output.name} is already emitted by "
            f"{existing!r}; {owner!r} may not also claim it. One edge has one "
            f"owner, or consumers cannot arbitrate between duplicates."
        )
    _EDGE_OWNERS[output] = owner


def edge_owner(output: DatasetRef) -> str | None:
    return _EDGE_OWNERS.get(output)


def reset_edge_owners() -> None:
    """Clear the registry. For tests; production registers once at startup."""
    _EDGE_OWNERS.clear()


# --------------------------------------------------------------------------
# Provenance run facet
# --------------------------------------------------------------------------


@attr.define
class ProvenanceRunFacet(RunFacet):
    """Carries an NG-0.1 envelope onto the lineage event.

    Building the facet from a `ProvenanceEnvelope` means the never-fabricate
    rule applies to lineage for free: an identifier the boundary does not have
    cannot be invented into a facet, and an absent one arrives with its reason.
    """

    identifiers: dict[str, object] = attr.field(factory=dict)
    absent: dict[str, str] = attr.field(factory=dict)

    @staticmethod
    def _get_schema() -> str:
        return f"{PRODUCER}/blob/main/docs/LINEAGE.md#provenance-run-facet"


def provenance_facet(envelope: prov.ProvenanceEnvelope) -> ProvenanceRunFacet:
    return ProvenanceRunFacet(
        identifiers=dict(envelope.to_dict()),
        absent=dict(envelope.reasons()),
    )


# --------------------------------------------------------------------------
# The emitter
# --------------------------------------------------------------------------


class LineageEmitter:
    """Emits OpenLineage events without ever endangering the data path.

    The transport is whatever ``OPENLINEAGE__TRANSPORT__*`` configures - a file
    in this change, an HTTP backend once NG-0.3 exists. That indirection is the
    point: changing backend must not mean rewriting emitters.
    """

    def __init__(
        self,
        job_name: str,
        *,
        client: OpenLineageClient | None = None,
        disabled: bool | None = None,
        namespace: str = JOB_NAMESPACE,
    ) -> None:
        self.job_name = job_name
        self.namespace = namespace
        self.disabled = LINEAGE_DISABLED if disabled is None else disabled
        self.failures = 0
        self.emitted = 0
        self._client = client
        self._client_failed = False

    def client(self) -> OpenLineageClient | None:
        """Build the client lazily, so a misconfigured transport cannot stop a
        service from starting."""
        if self._client is None and not self._client_failed:
            try:
                self._client = OpenLineageClient()
            except Exception as exc:
                self._client_failed = True
                self._note_failure("client construction", exc)
        return self._client

    def _note_failure(self, what: str, exc: BaseException) -> None:
        self.failures += 1
        print(
            f"Lineage {what} failed ({self.job_name}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )

    def emit(
        self,
        *,
        run_id: str,
        event_type: RunState,
        inputs: list[DatasetRef] | None = None,
        outputs: list[DatasetRef] | None = None,
        envelope: prov.ProvenanceEnvelope | None = None,
    ) -> bool:
        """Emit one event, reporting whether it was delivered.

        Never raises. A caller on the data path must be able to write this line
        and then reason about nothing else.
        """
        if self.disabled:
            return False
        try:
            client = self.client()
            if client is None:
                return False
            facets: dict[str, RunFacet] = {}
            if envelope is not None:
                facets["provenance"] = provenance_facet(envelope)
            event = RunEvent(
                eventTime=datetime.now(timezone.utc).isoformat(),
                eventType=event_type,
                producer=PRODUCER,
                run=Run(runId=run_id, facets=facets),
                job=Job(namespace=self.namespace, name=self.job_name),
                inputs=[ref.as_input() for ref in (inputs or [])],
                outputs=[ref.as_output() for ref in (outputs or [])],
            )
            client.emit(event)
        except Exception as exc:
            self._note_failure("emission", exc)
            return False
        self.emitted += 1
        return True


def run_id_for(seed: str) -> str:
    """A lineage run id derived from the boundary's own identifier.

    OpenLineage requires a UUID, while this platform's runs are identified by a
    ``load_id`` or ``cycle_id``. Deriving the UUID from that identifier keeps
    the two joinable after the fact and makes a retry of the same work emit the
    same run id rather than a second unrelated run.
    """
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{PRODUCER}/run/{seed}"))
