## Context

NG-0.2 has a failure mode worth naming before designing around it: lineage that
looks right. A graph assembled from static topology renders beautifully and
proves nothing, because it says what the code *would* do rather than what a run
*did*. The item forbids that directly — "static DAG topology SHALL NOT be
presented as proof that a particular runtime read/write occurred" — so every
decision below is pushed toward events that carry identifiers only a real
execution could have.

## Freshness of external assumptions

The item requires each time-sensitive premise to be re-verified at promotion
rather than carried on the authority of the backlog. Re-verified 2026-08-20
against primary sources:

| Premise as recorded | Verdict | Evidence |
|---|---|---|
| Airflow 3.x uses `apache-airflow-providers-openlineage`, not legacy `openlineage-airflow` | **Holds** | Provider 2.20.0 requires `apache-airflow>=2.11.0`, supports Python 3.12 |
| The provider is installable here | **Holds, and cheaply** | Resolves against the pinned Airflow 3.3.1 environment adding exactly one package and changing no existing pin |
| `openlineage-python` must be added to the Airflow image | **Refuted** | Already present at 1.52.0, pulled transitively by `astronomer-cosmos==1.15.0`. The provider's floor is `>=1.52.0` — satisfied exactly |
| OpenLineage provides a usable Spark integration for this stack | **Refuted** | Build declares variants `spark3`…`spark40`; `gradle.properties` pins `spark40.spark.version=4.0.0`. No `spark41`/`spark42`. This repo runs Spark 4.2.0 |
| A backend is needed to capture events | **Refuted** | The client's `file` transport with `append: true` writes newline-delimited JSON, which is a receipt without deploying NG-0.3 early |

The Spark row is the one that changes the shape of the change, and it is
recorded as a refutation rather than a difficulty.

## Decisions

**The Spark listener is not installed, and the missing edge is named.** The
choice is between an unproven binary-compatibility bet on the most
safety-critical service in the repository — the B2 exactly-once streaming job
with its checkpoints and FF-14 conflict handling — and an explicitly recorded
gap. The item pre-decided this: when the listener is incompatible, "the
integration remains disabled" and the blocker is documented "rather than
downgrading Spark silently".

So `Kafka → landing` is absent from the emitted graph. It is absent the way
NG-0.1 requires absence to work: named, with a reason, in `docs/LINEAGE.md`.

The tempting alternative is worth recording as rejected. The writer *could*
emit a `Kafka → bronze` edge, because Bronze rows carry `kafka_partition` and
`kafka_offset` and the offset range of an ingested batch is right there. That
would close the graph on the diagram and be false: the writer never read Kafka.
It reads Parquet files from a landing prefix. Attributing an edge to a job that
did not perform it is exactly the defect the item's "lineage SHALL reflect
actual runs" requirement exists to prevent, and a lineage graph that lies about
which job did what is worse than one with a labelled hole.

That the Kafka-to-Iceberg *data* provenance is already provable is what makes
the hole tolerable: NG-0.1's receipt establishes Kafka position → `load_id` →
snapshot from stored state. What is missing here is the lineage *event* for that
hop, not the ability to trace it.

**Emission uses the official client, not hand-rolled JSON.** Hand-building event
dictionaries would avoid a dependency in the iceberg image, and would mean
owning the schema and writing a transport. The item requires "transport/backend
change without emitter redesign", which is precisely what the client's transport
abstraction provides: this change writes to a file, NG-0.3 changes one
environment variable to point at OpenMetadata, and no emitter code changes.

**The emitter is fail-open, and that is a deliberate asymmetry.** Everywhere else
this repository fails closed. Lineage inverts it, because the failure being
guarded against is different: a lineage backend outage must never become a data
outage. NG-0.1 already fixed this as a rule — metadata systems are consumers of
data-plane state, and their unavailability "reduces observability; it never
corrupts canonical data".

So every emit is wrapped, every exception is swallowed after being logged and
counted, and the counter is what makes the silence observable. An emitter that
fails silently and invisibly would trade a data outage for an undetectable
lineage outage, which is why the metric is part of the contract and not a nicety.

**One edge has exactly one owner, enforced at import time.** The item asks for a
negative test for duplicate emitters on the same edge. A test alone would catch
it in CI; a registry catches it at process start. `register_edge_owner()` maps an
output dataset to the boundary that produces it and raises if a second boundary
claims it. This is what makes "no duplicate ingestion of the same lineage edge"
a structural property rather than a review convention, and it is what will fail
loudly when NG-0.3 adds dbt lineage that could otherwise double-count the
warehouse edges.

**Dataset names are built from configuration, never from the runtime host.** The
item forbids "avoidable aliases caused by hostnames or ephemeral container IDs".
The temptation is `socket.gethostname()`, which in Compose yields a container id
and would make the same table appear under a new alias on every restart. Names
come from configured endpoints — the catalog URI, the bucket, the Kafka
bootstrap — normalised to strip credentials, ports and scheme variants, so
`s3a://` and `s3://` forms of one bucket do not fork.

**Run facets carry NG-0.1 envelopes.** The run facet is built from a
`ProvenanceEnvelope`, which means the fabrication rules are enforced on lineage
events for free: an identifier the boundary does not have cannot be invented
into a facet, and an absent one carries its reason. This is the first consumer
of NG-0.1's contract, and it is why NG-0.1 was a real dependency rather than a
sequencing preference.

## Risks / Trade-offs

**The acceptance graph is closed except at its first hop.** Three of the four
edges are emitted from the boundary that performs them; the fourth is documented
as blocked with primary-source evidence. This is an incomplete item by its own
acceptance text, and the evidence records it as such rather than presenting the
remaining edges as the whole.

**The Airflow provider emits for orchestrated tasks only.** The medallion and
writer are long-running services, not Airflow tasks, so their lineage comes from
their own emitters. Two producers therefore write into one event stream, which
is exactly the condition the edge-ownership registry exists to police.

**File transport is a receipt, not a backend.** Events accumulate in a JSONL
file with no retention, query or dedup. That is adequate for proving the graph
and inadequate as an operational surface, which is NG-0.3's job. The risk is
someone reading the file's existence as a lineage capability.

**Coverage of the emitters is unit-level plus one live receipt.** The captured
event JSON tests prove shape and content; the receipt proves the events appear
in a real run. Neither proves behaviour under sustained load, which no test here
claims.
