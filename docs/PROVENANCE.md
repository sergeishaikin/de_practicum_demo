# Platform provenance and identity contract

One cross-system vocabulary, so that a processing result can be traced to the
code, the execution, the input transport position and the canonical Iceberg state
that produced it — without any of those identifiers becoming an operational
liability.

The executable half of this document is
[`iceberg/common/provenance.py`](../iceberg/common/provenance.py), exercised by
[`tests/test_provenance_contract.py`](../tests/test_provenance_contract.py) and
[`tests/integration/test_provenance_receipt.py`](../tests/integration/test_provenance_receipt.py).
Where the two disagree, the code is the contract and this file is the defect.

## Why link identifiers rather than unify them

The platform already had useful identities before this contract — `cycle_id`,
`load_id`, Iceberg snapshot ids, Kafka offsets, Airflow run ids. They were not
one contract, and the tempting fix is to make everything share a single UUID.

That fix is wrong. An OpenTelemetry `trace_id` is not a substitute for business
run identity: it is created and discarded by telemetry, and telemetry may be
absent while processing is correct. An OpenLineage run id is not a substitute for
a medallion `cycle_id`: the lineage event describes the cycle, it does not
constitute it. Collapsing them would make the platform's correctness depend on a
control plane that NG-0.1 explicitly requires it to survive without.

So identifiers are **linked, not merged**. Each system keeps the identity it
actually owns, and the relationship between them is recorded explicitly.

## Canonical vocabulary

Names come from `provenance.CANONICAL_FIELDS`; an envelope refuses any name
outside it, so two systems cannot describe one concern differently.

| Field | Authoritative for | Owned by |
|---|---|---|
| `platform.run_id` | logical correlation across one execution, where one exists | the process that starts the execution |
| `airflow.dag_id` / `airflow.dag_run_id` / `airflow.task_id` | orchestrated execution identity | Airflow |
| `cycle_id` | one medallion cycle, including cycles Airflow never launched | the medallion loop |
| `load_id` | one writer append and its recovery state | the Iceberg writer |
| `code.revision` | which code produced the result | git / the build |
| `trace_id` / `span_id` | telemetry correlation only | OpenTelemetry (NG-0.4) |
| `lineage.job_namespace` / `lineage.job_name` / `lineage.run_id` | lineage event identity | OpenLineage (NG-0.2) |
| `dataset.namespace` / `dataset.name` | a dataset's stable name across systems | this contract |
| `kafka.topic` / `kafka.partition` / `kafka.offset` | input transport position | Kafka |
| `iceberg.table` / `iceberg.snapshot_id` | **the state an event is about**: the snapshot the emitting boundary committed | Iceberg |
| `iceberg.source_snapshot_id` | **the state a result was computed from** | Iceberg |
| `dbt.invocation_id` / `dbt.model` | warehouse transform identity | dbt |

### Cross-references are explicit

When two systems identify the same execution differently, **both** identifiers
are preserved and the relationship is emitted. Neither replaces the other. An
Airflow task that triggers a medallion cycle records `airflow.dag_run_id` *and*
`cycle_id`; it does not rename one to the other.

## An envelope never fabricates

A provenance envelope carries the identifiers available at one boundary. What is
unavailable is **absent, with a recorded reason** — never derived from an
unrelated timestamp or counter.

```python
ProvenanceEnvelope(
    values={CYCLE_ID: "cyc-1", CODE_REVISION: "abc1234"},
    unknown={DAG_RUN_ID: "cycle was not launched by Airflow"},
)
```

The envelope enforces this: a null value is refused, a field cannot be both known
and unknown, and an unknown declared without a reason is refused — "unavailable"
with no reason is indistinguishable from "forgotten".

The reason is the part that survives to the reader. A later operator finding
`dag_run_id` absent can tell a background cycle from a lost identifier; finding a
plausible-looking fabricated value, they cannot tell anything at all.

## Iceberg snapshot is the version primitive

For structured lakehouse data, `iceberg.snapshot_id` is the primary
reproducibility reference. A mutable `latest` reference is not evidence.

This is why **DVC and lakeFS are not adopted**: Iceberg snapshots already address
the datasets in question reproducibly. Either becomes arguable only for data that
is not Iceberg-resident, and that argument needs its own evidence.

The writer stamps `load-id` into each append's snapshot summary. That stamp is
what joins transport position to stored state — without it, `kafka.offset` and
`iceberg.snapshot_id` are two unrelated facts about the same append.

A transformation has **two** snapshots, and one name cannot carry both. NG-0.2
surfaced this: a Bronze-to-Silver lineage event names the Bronze state it read
and the Silver state it wrote. `iceberg.snapshot_id` is the state the event is
about — what the boundary committed — and `iceberg.source_snapshot_id` is the
state it read. A boundary that merely appends, like the writer, has only the
former.

## Cardinality-safe telemetry

`platform.run_id`, `airflow.dag_run_id`, `cycle_id`, `load_id`, `trace_id`,
`span_id`, `lineage.run_id`, `kafka.offset`, `iceberg.snapshot_id`,
`dbt.invocation_id` and business keys such as `order_id` **SHALL NOT** become
Prometheus label values. Each grows without bound in the dimension Prometheus
charges for.

They belong in structured logs, trace attributes and events, exemplars,
OpenLineage facets, evidence artifacts, or a table designed for high-cardinality
data — `marts.lakehouse_metrics` already is one.

A metric that needs to reach one representative execution uses an exemplar or a
UI correlation, not a label.

This is enforced: `test_no_declared_prometheus_label_is_high_cardinality` parses
every metric declaration in `iceberg/common/ops.py` and
`observability/postgres_exporter.py` and fails on a forbidden label name.

## Data plane and control plane

Metadata, lineage and observability systems are **consumers** of data-plane state
unless a later change explicitly grants write ownership. Their unavailability
reduces observability; it never corrupts canonical data or changes
business-resolution semantics.

Concretely: a metrics write failure is logged and does not fail ingestion. That
behaviour predates this contract and is now a rule rather than an accident.

## Reproducibility rules

- **Images** carry explicit versions; `latest` never appears in committed
  Compose. Enforced by `test_committed_compose_pins_every_image`.
- **Secrets** come from environment or secret material, never committed, and
  control-plane credentials are independent of application superuser credentials
  wherever the product supports least privilege.
- **Heavyweight capabilities** arrive behind an opt-in Compose profile with a
  measured resource receipt before any proposal to join the default stack.

## What this contract does not yet cover

Recorded so absence is not mistaken for completeness:

- **No semantic-convention pinning yet.** The rule exists — an emitted
  convention version is pinned and tested — but there is no OTel instrumentation
  to pin. NG-0.4 introduces it.
- **`platform.run_id` has no producer.** The vocabulary reserves the name; no
  boundary emits one today, and an envelope that lacks it says so.
- **Only the writer boundary is proven end to end.** The receipt covers
  Kafka → `load_id` → snapshot. Medallion and dbt boundaries have their
  identifiers but no equivalent executable receipt.
- **No measured profile receipts exist.** No optional profile has been built yet,
  so the resource-isolation rule is stated and unexercised.
