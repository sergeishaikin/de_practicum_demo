## Verification receipt

NG-0.2's implementation landed in `7c1c18b`, its test corrections in `2746df1`
and `9c31999`, and it was last verified in full on `cffdb10`.

| Run | Workflow | Conclusion | SHA |
|---|---|---|---|
| [32350817903](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32350817903) | CI | success | `7c1c18b` |
| [32350817598](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32350817598) | H1 clean reproducible stack | success | `7c1c18b` |
| [32352344096](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32352344096) | H1 clean reproducible stack | **failure** | `2746df1` |
| [32353967937](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32353967937) | H1 clean reproducible stack | success | `9c31999` |
| [32355807568](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32355807568) | CI | success | `cffdb10` |
| [32355807524](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32355807524) | H1 clean reproducible stack | success | `cffdb10` |

The failure is listed deliberately. `2746df1` added an Airflow provider smoke
that asserted against `ListenerManager.listeners`, which does not exist in
Airflow 3.3. It was a defect in the test, not in the integration, and it was
fixed by interrogating a live Airflow image rather than by retrying CI.

Host gate on `cffdb10`: ruff and black clean, `mypy` clean over 9 source files,
**497 passed**, coverage **94.65%** — up from 94.48% before this item.

### The graph, read out of a running stack

H1's integration suite grew from 25 tests to 35 as this item landed:

```text
tests/integration/test_airflow_lineage_provider.py .....   [ 13%]
tests/integration/test_lineage_receipt.py .....            [ 50%]
============ 35 passed, 1 xfailed in 172.53s ============
```

The receipt reconstructs the graph from events the services themselves emitted
and asserts the path is *connected* — the output of each hop being the input of
the next — rather than asserting three unrelated edges exist:

```text
streaming/orders_raw ──▶ bronze.orders ──▶ silver.orders_clean ──▶ gold.orders_daily_metrics
      iceberg-writer        iceberg-medallion        iceberg-medallion
```

### Local live verification, and where it stopped

Per the local-first policy the same pipeline was run on the development host.
Both medallion edges emitted against a live REST catalog and object store:

```text
events: 10
  iceberg-medallion.bronze-to-silver: 5
  iceberg-medallion.silver-to-gold:   5

runId: 955a1688-50d6-5c16-bc21-3f03df9ac721
identifiers: {"cycle_id": "509bf9fb…",
              "iceberg.snapshot_id":        2990544206037659790,
              "iceberg.source_snapshot_id":  229477954253566003,
              "iceberg.table": "silver.orders_clean"}
absent:      {"airflow.dag_run_id": "the medallion is a continuous service…",
              "trace_id": "no tracing backend exists yet; NG-0.4 introduces one"}

5 distinct cycle ids -> 10 distinct run ids
```

That is the property static topology cannot fake: real snapshot ids, a source
snapshot genuinely different from the produced one, and one lineage run per
cycle per job rather than every execution collapsing into a single run.

**The `landing → bronze` edge was not reproduced locally.** The local Spark
streaming job aborts with
`KafkaIllegalStateException: Some data may have been lost because they are not
available in Kafka any more` — its checkpoint references offsets from a stack
last run on 2026-08-09, which the Kafka volume no longer holds. No new landing
files are written, so the writer has nothing to ingest and emits nothing.

That is stale local state, not a defect in this change, and it was **not**
worked around. Setting `KAFKA_FAIL_ON_DATA_LOSS=false` would trade a data-safety
guarantee for a green local run, and resetting the volumes would destroy the
operator's local lakehouse. The edge is proven in H1, which builds on fresh
volumes; locally it is recorded as unreproduced with the reason above.

One further local-only finding: the first attempt started the emitters with
`--no-build` against an image predating `openlineage-python`, and both services
died on `ModuleNotFoundError: No module named 'openlineage'`. A local run must
rebuild after a requirements change; CI always does.

### The Airflow provider is active, not merely installed

A passing DagBag proves the image builds. The running scheduler was asked
directly:

```text
provider_registered: True
listener_names:      ['cosmos.listeners.task_instance_listener',
                      'airflow.providers.openlineage.plugins.listener',
                      'cosmos.listeners.dag_run_listener']
transport:           {'type': 'file',
                      'log_file_path': '/opt/airflow/lineage/events.jsonl',
                      'append': True}
namespace:           de-practicum
disabled:            False
```

The listener is registered only when the OpenLineage configuration is present,
so this checks the deployed configuration rather than the installed package.

### Negative proofs

- **Duplicate emitters.** `register_edge_owner` raises when a second boundary
  claims an output another already claims, and the receipt independently asserts
  no dataset in the emitted stream carries two owning jobs.
- **Backend down.** An unreachable transport returns `False`, increments the
  failure counter and never raises — asserted against a real refused connection,
  not a mock.
- **An emitter that raises internally** is absorbed and counted.
- **A misattributed edge.** The receipt asserts that *no* job claims a Kafka
  input, because the writer holds `kafka_offset` on every Bronze row and could
  derive that edge. Omitting the check would not notice a later change starting
  to fabricate it.
- **Aliasing.** Six spellings of the REST catalog and four of the bucket resolve
  to one identity; two genuinely different hosts stay two datasets, so
  normalisation has not become erasure.

### The edge this item does not close

`Kafka → streaming job → landing` is **not emitted**, and the receipt asserts
its absence rather than omitting the subject.

Verified against primary sources on 2026-08-20: OpenLineage's Spark integration
builds variants `spark3` … `spark40`, with `gradle.properties` pinning
`spark40.spark.version=4.0.0`. There is no `spark41` or `spark42` module, and
this repository runs Spark **4.2.0**. The item's own scenario governs that case:
the integration stays disabled and the blocker is documented rather than the
engine being changed to suit the tool.

The rejected alternative is recorded in `design.md`: the writer *could* emit a
Kafka-to-Bronze edge from the offsets on its rows, and it never read Kafka.

This gap concerns the lineage *event*, not traceability. NG-0.1's receipt
already proves Kafka position → `load_id` → snapshot from stored state.

### Vocabulary change

NG-0.1's `iceberg.snapshot_id` was documented as "the state a result was
computed from" while its own receipt used it for the snapshot *produced*. A
transformation has both, and one name cannot carry two concerns, so
`iceberg.source_snapshot_id` was added to `CANONICAL_FIELDS`,
`HIGH_CARDINALITY_FIELDS`, `FORBIDDEN_LABEL_NAMES` and `docs/PROVENANCE.md`
together — the friction NG-0.1 designed for, working as intended.

### What this does not establish

- **No sustained-load behaviour.** The receipt proves the events appear in a
  real run; nothing here measures emission cost under load.
- **No Airflow task lineage event was observed.** DAGs are paused at creation,
  so no task ran in CI, and triggering one would mutate stack state the
  surrounding tests depend on. The provider is proven configured and active;
  its emission is not proven end to end.
- **The file transport is a receipt, not a backend.** No retention, query or
  deduplication. NG-0.3 repoints the same emitters at OpenMetadata by changing
  configuration.
- **`docs/LINEAGE.md` predates this item** and remains a descriptive record;
  only its OpenLineage section and the deferred-work rows were updated.
