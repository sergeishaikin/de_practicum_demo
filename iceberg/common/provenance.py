"""The platform's identity and provenance contract, as executable code.

Prose can describe which identifier is authoritative for which concern; it cannot
stop a later boundary from inventing a value it does not have, or from turning a
per-execution identifier into an unbounded Prometheus label. Both of those are
failure modes this repository can already reach, so the parts of NG-0.1 that can
be checked live here rather than only in `docs/PROVENANCE.md`.

Two rules carry the weight:

**An envelope never fabricates.** An identifier that is not available at a
boundary is absent, with a recorded reason. It is never derived from an unrelated
timestamp or counter, because a reader cannot tell a derived value from a real
one, and a provenance record that might be inferred is worth less than one that
is admittedly incomplete.

**High-cardinality identity never becomes a metric dimension.** `load_id`,
`cycle_id`, business keys and Kafka offsets are unbounded in the dimension that
matters to Prometheus. They belong in structured logs, trace attributes,
exemplars, lineage facets and tables built for them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

# --------------------------------------------------------------------------
# Canonical vocabulary
# --------------------------------------------------------------------------
# One name per concern, so two systems cannot describe the same thing
# differently. `docs/PROVENANCE.md` states which identifier is authoritative for
# which concern; this is the machine-readable half of that table.

PLATFORM_RUN_ID = "platform.run_id"
DAG_ID = "airflow.dag_id"
DAG_RUN_ID = "airflow.dag_run_id"
TASK_ID = "airflow.task_id"
CYCLE_ID = "cycle_id"
LOAD_ID = "load_id"
CODE_REVISION = "code.revision"
TRACE_ID = "trace_id"
SPAN_ID = "span_id"
LINEAGE_JOB_NAMESPACE = "lineage.job_namespace"
LINEAGE_JOB_NAME = "lineage.job_name"
LINEAGE_RUN_ID = "lineage.run_id"
DATASET_NAMESPACE = "dataset.namespace"
DATASET_NAME = "dataset.name"
KAFKA_TOPIC = "kafka.topic"
KAFKA_PARTITION = "kafka.partition"
KAFKA_OFFSET = "kafka.offset"
ICEBERG_TABLE = "iceberg.table"
# The snapshot an event is *about*: the one the emitting boundary committed.
ICEBERG_SNAPSHOT_ID = "iceberg.snapshot_id"
# The snapshot a result was *computed from*. Distinct from the one above because
# a transformation has both, and NG-0.2 surfaced that one name cannot carry two
# concerns: a Bronze-to-Silver event names the Bronze state it read and the
# Silver state it wrote, and conflating them makes the lineage unreadable.
ICEBERG_SOURCE_SNAPSHOT_ID = "iceberg.source_snapshot_id"
DBT_INVOCATION_ID = "dbt.invocation_id"
DBT_MODEL = "dbt.model"

CANONICAL_FIELDS: frozenset[str] = frozenset(
    {
        PLATFORM_RUN_ID,
        DAG_ID,
        DAG_RUN_ID,
        TASK_ID,
        CYCLE_ID,
        LOAD_ID,
        CODE_REVISION,
        TRACE_ID,
        SPAN_ID,
        LINEAGE_JOB_NAMESPACE,
        LINEAGE_JOB_NAME,
        LINEAGE_RUN_ID,
        DATASET_NAMESPACE,
        DATASET_NAME,
        KAFKA_TOPIC,
        KAFKA_PARTITION,
        KAFKA_OFFSET,
        ICEBERG_TABLE,
        ICEBERG_SNAPSHOT_ID,
        ICEBERG_SOURCE_SNAPSHOT_ID,
        DBT_INVOCATION_ID,
        DBT_MODEL,
    }
)

# Unbounded, or bounded only by how much the platform has processed. None of
# these may become a Prometheus label value; all of them may appear in logs,
# trace attributes, exemplars, lineage facets or a table designed for them.
HIGH_CARDINALITY_FIELDS: frozenset[str] = frozenset(
    {
        PLATFORM_RUN_ID,
        DAG_RUN_ID,
        CYCLE_ID,
        LOAD_ID,
        TRACE_ID,
        SPAN_ID,
        LINEAGE_RUN_ID,
        KAFKA_OFFSET,
        ICEBERG_SNAPSHOT_ID,
        ICEBERG_SOURCE_SNAPSHOT_ID,
        DBT_INVOCATION_ID,
    }
)

# The bare names a metric label is likely to use, mapped from the canonical
# dotted form, so a cardinality check can recognise `load_id` as readily as
# `load.id`. Business keys are included: `order_id` is the one this platform has.
FORBIDDEN_LABEL_NAMES: frozenset[str] = frozenset(
    {
        "business_key",
        "cycle_id",
        "dag_run_id",
        "dbt_invocation_id",
        "invocation_id",
        "kafka_offset",
        "load_id",
        "offset",
        "order_id",
        "run_id",
        "snapshot_id",
        "source_snapshot_id",
        "span_id",
        "trace_id",
    }
)


class ProvenanceError(ValueError):
    """A provenance envelope was asked to record something it cannot honour."""


@dataclass(frozen=True)
class ProvenanceEnvelope:
    """The identifiers available at one processing boundary.

    Every field is optional because no single boundary has all of them: a
    medallion cycle started by its own loop has a `cycle_id` and no
    `airflow.dag_run_id`, and inventing one would be a lie a later reader could
    not detect.

    An identifier that is unavailable is declared in ``unknown`` with the reason.
    That is deliberately more work than omitting it silently - the reason is the
    part that survives to the reader.
    """

    values: Mapping[str, object] = field(default_factory=dict)
    unknown: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unrecognised = sorted(set(self.values) - CANONICAL_FIELDS)
        if unrecognised:
            raise ProvenanceError(
                f"not in the canonical vocabulary: {unrecognised}. Add the field "
                "to CANONICAL_FIELDS and to docs/PROVENANCE.md, or use the "
                "existing name for this concern."
            )

        unrecognised_unknown = sorted(set(self.unknown) - CANONICAL_FIELDS)
        if unrecognised_unknown:
            raise ProvenanceError(
                f"declared unknown but not in the vocabulary: {unrecognised_unknown}"
            )

        both = sorted(set(self.values) & set(self.unknown))
        if both:
            raise ProvenanceError(
                f"recorded as both known and unknown: {both}. A field is one or "
                "the other; a value with a reason attached reads as a guess."
            )

        empty_reasons = sorted(f for f, why in self.unknown.items() if not why.strip())
        if empty_reasons:
            raise ProvenanceError(
                f"declared unknown without a reason: {empty_reasons}. 'Unavailable' "
                "with no reason is indistinguishable from 'forgotten'."
            )

        none_values = sorted(f for f, v in self.values.items() if v is None)
        if none_values:
            raise ProvenanceError(
                f"present with a null value: {none_values}. Absence is expressed "
                "by omission plus a reason in `unknown`, not by a null."
            )

        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
        object.__setattr__(self, "unknown", MappingProxyType(dict(self.unknown)))

    def to_dict(self) -> dict[str, object]:
        """The identifiers actually available, and nothing else.

        Unknown fields are absent from the result rather than present as null, so
        a consumer cannot mistake "we did not have it" for "it was empty".
        """

        return dict(self.values)

    def reasons(self) -> dict[str, str]:
        """Why each absent identifier is absent."""

        return dict(self.unknown)

    def requires(self, *fields: str) -> ProvenanceEnvelope:
        """Assert that this boundary really does carry the named identifiers.

        Used where a contract says a particular envelope must be complete - a
        Bronze append knows its `load_id` and its snapshot - so a regression that
        drops one fails at the boundary rather than in a dashboard weeks later.
        """

        missing = sorted(f for f in fields if f not in self.values)
        if missing:
            raise ProvenanceError(f"required identifiers missing: {missing}")
        return self


def cardinality_violations(label_names: object) -> list[str]:
    """Label names that would put per-execution identity into a metric series.

    Returns the offenders rather than raising, so a caller can report every
    violation in one pass instead of one per run.
    """

    if isinstance(label_names, str) or not hasattr(label_names, "__iter__"):
        raise ProvenanceError(
            f"expected an iterable of label names, got {label_names!r}"
        )

    violations = []
    for name in label_names:
        candidate = str(name).strip().lower()
        if candidate in FORBIDDEN_LABEL_NAMES:
            violations.append(str(name))
    return sorted(violations)
