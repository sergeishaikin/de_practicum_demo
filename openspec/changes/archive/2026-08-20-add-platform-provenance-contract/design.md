## Context

NG-0.1 is a contract item, and contract items have a characteristic failure: they
produce a document everyone agrees with and nothing that can fail. The item
anticipates this — its acceptance evidence asks for *executable* validation, a
*negative* test, and an end-to-end *receipt*, not a specification.

So the question is which parts of the contract can be made to fail, and the
answer shapes everything below.

## Decisions

**Identifiers are linked, not merged, and the document argues for it.** The
tempting simplification is one UUID everywhere. It is wrong for a reason worth
writing down: a `trace_id` is created and discarded by telemetry, and telemetry
may be absent while processing is correct. Merging business identity into it
would make correctness depend on a control plane NG-0.1 requires the platform to
survive without. The same argument rules out an OpenLineage run id standing in
for `cycle_id`.

**The envelope refuses rather than warns.** `ProvenanceEnvelope` raises on a
null value, on a field that is both known and unknown, on an unknown without a
reason, and on a name outside the vocabulary. A warning would be ignored; the
whole value of "never fabricates" is that it cannot be done by accident.

Requiring a *reason* for each absent field is deliberately more work than
omitting it. The reason is the part that survives: an operator who finds
`dag_run_id` absent with "cycle was not launched by Airflow" learns something,
where absence alone is indistinguishable from a lost identifier.

**The cardinality test parses rather than imports.** Importing
`observability/postgres_exporter.py` constructs real collectors, and `ops.py`
would bind a socket. The property under test is what the source *declares*, and
an AST walk sees exactly that. It also reports every violation in one pass rather
than one per run.

The metric sources are **listed, not globbed**, so a new metrics surface fails
the test until someone adds it deliberately — and a companion test asserts the
listed files exist, so a rename fails loudly instead of silently checking
nothing. That guard earned itself immediately: the first draft pointed at
`observability/exporter.py`, which does not exist, and the test caught it.

**`FORBIDDEN_LABEL_NAMES` holds bare names, not the dotted vocabulary.** A metric
label will be written `load_id`, not `load.id`. Matching is
case-insensitive and includes `order_id`, the business key this platform actually
has.

**The receipt is an integration test, not a committed artifact.** No live stack
is available in this environment, and the item's chain is only meaningful if each
hop is read back out of the platform. As a test it runs wherever the stack does —
CI — and fails if the chain breaks. A committed JSON file would prove the chain
held once, on a machine, in the past.

The middle hop is the one worth guarding. `kafka_offset` and `snapshot_id` are
both recorded today; the `load-id` snapshot stamp is what joins them, and without
it the two are unrelated facts about the same append.

**The contract is not retrofitted onto existing boundaries.** The envelope exists
for boundaries to adopt; rewriting the writer and medallion to emit one is
per-boundary work with real behaviour risk, and burying it inside a contract
change would make the diff unreviewable. Recorded in the document under what the
contract does not yet cover.

## Risks / Trade-offs

**A contract nothing emits yet.** `ProvenanceEnvelope` is used by its tests and
the receipt, not by production boundaries. That is honest — the item asks for the
contract and its validation, and the alternative was a behaviour change disguised
as documentation — but a reader could mistake the module's existence for the
platform emitting envelopes. The document says plainly that it does not.

**The cardinality test can be evaded.** A label built at runtime from a variable
would not appear as a string constant in the AST. The test catches the way
metrics are actually declared in this repository — all ten label sets are
literals — and would need extending if that changed.

**The vocabulary will need to grow.** NG-0.2 and NG-0.4 will want fields that do
not exist yet. `CANONICAL_FIELDS` refusing an unknown name makes that friction
visible, which is the intent: adding a name should require touching the contract
and the document together.
