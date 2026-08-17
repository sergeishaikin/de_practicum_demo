# W2 — Warehouse execution contract

What the batch warehouse path guarantees under replay, failure and recovery, and
where each guarantee is proven. This is the companion to `W1-dbt-ownership.md`,
which covers *what the SQL computes*; this document covers *what happens when a
run is repeated, interrupted or retried*.

## The contract

| Property | Guarantee | Proven by |
|---|---|---|
| Replaying the same batch | **Idempotent** — identical final business state, not rejected | `assert_replay_parity.sql` (SQL level, `ci-pr.yml`) and a real re-trigger of `warehouse_orders_ingestion` (`ci-integration.yml`) |
| Staging accumulation | **Impossible** — `00_truncate_stg.sql` runs before every CSV copy | Scenario *"Staging load truncates before every batch…"* |
| Core accumulation | **Impossible** — `10_rebuild_core.sql` truncates `core.*` inside its transaction | `assert_replay_parity.sql` row-count guards |
| Retried DagRun audit | **Converges** — `on conflict (run_id) do update` | Scenario *"Re-running the same DagRun updates the audit row…"* |
| dbt validation failure | **No publication** — no audit row, no Assets | Scenario *"Mart publication is refused when dbt validation did not succeed"* |
| Recovery after failure | **Full publication** — audit written once, all five Assets | Scenario *"A recovered marts run publishes the same way a clean run does"* |
| Empty / mismatched staging | **Rejected before core** | Scenarios *"Empty staging is rejected"*, *"Mismatched staging is rejected"* |
| Unreadable core | **No Asset metadata** | Scenario *"Core readiness failure publishes no Asset metadata"* |
| Ambiguous Asset provenance | **Fails closed** | Scenario *"Ambiguous source events fail closed"* |
| Payment mismatch | **Blocks mart publication** | Scenario *"Payment mismatch prevents mart publication"* |

## Why replay is idempotent rather than rejected

The design choice is deliberate and worth stating, because the alternative —
rejecting a duplicate batch — would be a reasonable contract too.

`warehouse_orders_ingestion` is a **full-refresh** pipeline, not an incremental
one. Every run truncates `stg.*`, re-copies the same four CSVs, then truncates
and rebuilds `core.*` inside one transaction. Staging therefore holds exactly one
batch at any time. Nothing accumulates, so a second run of the same inputs
converges on the same state rather than doubling it.

That has a direct operational consequence: **an Airflow retry, a manual
re-trigger, or a rerun after a partial failure are all safe by construction.**
There is no duplicate-detection logic to get wrong, because there is no state for
a duplicate to corrupt.

The trade-off, stated plainly: because `stg` holds one batch, the pipeline cannot
represent a late-arriving item whose header shipped in an earlier CSV. Such an
item is dropped by the inner join in `10_rebuild_core.sql`. That is acceptable
for a full-refresh demo warehouse over static Olist CSVs, and would not be
acceptable for an incremental pipeline over a live feed. Changing to incremental
loading would invalidate every guarantee in the table above and require this
document to be rewritten first.

## The failure boundary that matters

The meaningful injection point is **after core is rebuilt and published, but
before the marts are published** — the window where the warehouse holds valid new
core data that has not yet been certified by dbt.

`publish_mart_assets` guards it explicitly: it reads the state of
`validate_dbt_artifacts` from the Airflow metadata database and raises before
doing anything else if that task did not succeed. The audit function is never
called, so `marts.pipeline_runs` gains no row, and no mart Asset is emitted —
nothing downstream can be triggered by a run whose data was never validated.

The recovery scenario asserts the mirror image: with validation successful the
audit is called exactly once and all five Assets (four marts plus the audit) are
published. A failed run followed by a successful one therefore lands in the same
state as a clean run.

## Where each layer is exercised

| Layer | Mechanism | Speed |
|---|---|---|
| Task callables with injected failures | Real DagBag loaded inside `de-demo-airflow`, fakes for the database | ~11 s per scenario, `ci-pr.yml` fast suite |
| SQL replay parity | Seed → real `10_rebuild_core.sql` → snapshot → rebuild → diff | seconds, `ci-pr.yml` |
| Whole pipeline through Airflow | `airflow dags trigger warehouse_orders_ingestion`, Asset-triggered marts run, then a second trigger of the same batch | minutes, `ci-integration.yml` |
| Staging load recency | `dbt source freshness` over `loaded_at`, configured on the four `stg.*` sources and wired as `check_source_freshness` upstream of the dbt build | **configured; not yet exercised** — see below |

The behavioural scenarios run against the **real task callables from the real
DagBag** — not a reimplementation — with only the database connection faked, so a
change to the production callable breaks the scenario.

## The load-recency gate, and what is not yet proven about it

The gate is **configured, not yet exercised**. `check_source_freshness` is
declared upstream of the `dbt_warehouse` group in `warehouse_marts_validation`,
and the four staging sources carry `loaded_at_field` with both thresholds. Two
proofs are deliberately still outstanding, and this document must not be read as
claiming either:

- the executable CI proof — a freshly seeded batch passing and a deliberately
  backdated batch exiting non-zero — lands with the CI steps, not here;
- the **runtime** dependency edge. `check_source_freshness >> dbt_group` is
  source-level wiring. What task set Cosmos actually expands `dbt_group` into,
  and therefore whether the real producer edge exists in the rendered DagBag, is
  proven only by observing a live DagBag. Until then this is a designed chain,
  not an observed one.

The chain it is designed to produce needs **no modification to any existing
guard**: a freshness failure makes the Cosmos producer `upstream_failed`;
`validate_dbt_artifacts` already treats `upstream_failed` as terminal and
raises; and `publish_mart_assets`, on trigger rule `ALL_DONE`, re-reads that
validation state and refuses before `_audit_and_counts` is ever called. So no
`marts.pipeline_runs` row and no mart Asset can claim success for a stale slice.
That the existing failure boundary already absorbs a new upstream failure
unchanged is the strongest argument for placing the gate here rather than in the
ingestion DAG.

`W1-dbt-ownership.md` remains the source of truth for why the gate exists, what
it deliberately does not promise, and why its thresholds are still provisional.

## Known gap

Cosmos 1.15 logs `Unavailable conversion function for <DbtResourceType.UNIT_TEST>`
when rendering the dbt graph: it does not map dbt unit tests to Airflow task
nodes. They still execute, because `ExecutionMode.WATCHER` runs the canonical
`dbt build`, which includes unit tests — but they are not individually visible in
the Airflow UI. This is a display limitation, not a coverage gap; the run-results
validation in `validate_dbt_artifacts` still fails the run if any of them fail.
