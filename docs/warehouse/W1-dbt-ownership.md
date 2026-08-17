# W1 — Warehouse dbt ownership

Status: implemented; the warehouse mart views and validation contracts are
owned by the dedicated `dbt/warehouse` project.

## Ownership boundary

`warehouse_orders_ingestion` remains responsible for loading the four CSV
inputs and executing the unchanged transactional `db/pipeline_sql/10_rebuild_core.sql`
core rebuild. Its successful `core.orders` Asset is the only schedule for
`warehouse_marts_validation`.

The Asset-triggered DAG uses Astronomer Cosmos 1.15.0 in
`ExecutionMode.WATCHER`. Cosmos renders the warehouse dbt graph and executes
the canonical `dbt build` command. dbt owns the four PostgreSQL mart views:

- `marts.v_order_items_wide`
- `marts.v_sales_daily`
- `marts.v_customer_state_daily`
- `marts.v_reconcile_sales_daily`

The final Airflow task runs only after dbt models and tests succeed. It checks
the legacy audit invariants, writes `marts.pipeline_runs`, and publishes the
four mart Assets plus the audit Asset. Missing or ambiguous core provenance,
dbt failure, artifact failure, or audit failure publishes nothing.

## dbt project and contracts

The project is `dbt/warehouse`, with pinned `dbt-core==1.12.2` and
`dbt-postgres==1.11.0`. PostgreSQL `stg.*` and `core.*` relations are declared
as sources and tagged with their Airflow ownership. The mart views preserve
the existing relation names and SQL semantics. Enforced model contracts cover
the published columns; singular tests cover source-to-mart sales
reconciliation, order-item grain, and staging-to-core payment reconciliation.

Selectors:

- `warehouse_contracts` — tier-1 mart contracts and descendants.
- `warehouse_reconciliation` — reconciliation models and tests.

## Testing layers

The project is tested at seven levels, each answering a different question. As
of this writing the project carries **4 models, 79 data tests and 9 unit
tests** (`dbt ls`).

**Unit tests** (`models/marts/unit_tests.yml`) — *does the SQL compute the right
thing?* Fixture rows are mocked for every `source()` and `ref()`, so no
warehouse data is involved. They pin the semantics that are easy to break and
invisible in a green production run:

| Unit test | Guards |
|---|---|
| `order_items_wide_keeps_items_without_a_matching_order` | the `LEFT JOIN` to `core.orders`; an inner join would silently drop items |
| `order_items_wide_enriches_every_item_of_its_order` | per-item enrichment across a multi-item order, and NULL payment propagation |
| `sales_daily_counts_orders_distinctly_and_sums_money_per_day` | `COUNT(DISTINCT order_id)` vs `COUNT(*)`, the money sums, and day grouping |
| `sales_daily_sums_money_exactly_not_in_floating_point` | `0.10 + 0.20` is exactly `0.30` in `numeric` and `0.30000000000000004` in binary floating point; fails if a money column becomes a float or double |
| `sales_daily_produces_no_rows_for_an_empty_source` | an empty source yields an empty mart, not one all-NULL aggregate row — which is what removing the `GROUP BY` would produce |
| `reconcile_sales_daily_reports_both_sides_of_the_full_join` | all four `FULL JOIN` branches, both `COALESCE`s, and the sign of `diff_amount` |
| `reconcile_sales_daily_ignores_cross_batch_ingest_dates` | the `ingest_date` predicate that keeps ingestion batches from cross-reconciling |
| `reconcile_sales_daily_is_empty_when_both_sides_are_empty` | nothing on either side produces nothing at all, rather than a zero-valued row that would falsely report a reconciled day |
| `customer_state_daily_partitions_each_day_by_state` | both grouping keys participate, and `orders_cnt` stays distinct-per-group rather than distinct-per-day |

**Data tests** — *do the real rows satisfy the contract?* Enforced model
contracts cover column shape. Column-level `not_null` / `unique` /
`non_negative` cover every staging and core column the pipeline depends on but
the DDL leaves nullable; the DDL's own primary keys are deliberately **not**
re-asserted, since PostgreSQL already enforces them and duplicating them adds
runtime with no new failure mode. `composite_unique` covers the
`(order_id, order_item_id)` and `(sales_date, customer_state)` grains — dbt's
built-in `unique` is single-column only and this project carries no packages, so
that generic test lives in `macros/`.

**Property tests** — *do relationships that must hold on any data still hold?*
Distinct from reconciliation, which asserts that today's rows agree:

| Test | Invariant |
|---|---|
| `reconcile_arithmetic_consistency.sql` | `mart − source − diff = 0`; the view cannot misreport its own arithmetic |
| `sales_daily_orders_within_items.sql` | `orders_cnt ≤ items_cnt`; catches the two counters being swapped |
| `order_items_wide_preserves_item_count.sql` | row count equals `core.order_items`, and names whether it was fan-out or row loss |
| `customer_state_rolls_up_to_sales_daily.sql` | the state grain sums back to the daily grain exactly |

`order_status` intentionally has no `accepted_values` test: the values in the
demo slice are a sample artifact and the full Olist domain is wider, so pinning
the observed set would fail on a legitimate fuller load.

**Integration check** — *does the whole chain still line up?* The `ci-pr.yml`
`warehouse-dbt-contract` job seeds `tests/fixtures/warehouse/seed_staging.sql`
(three orders, two days, two customer states, a multi-item order and a
multi-row payment), runs the production `db/pipeline_sql/10_rebuild_core.sql`
rather than a hand-written core insert, runs `dbt build`, then requires
`tests/fixtures/warehouse/assert_marts.sql` to return zero rows. That file
pins the exact expected `core.orders`, `v_sales_daily`,
`v_customer_state_daily`, `v_order_items_wide` and `v_reconcile_sales_daily`
tuples, including `diff_amount = 0` on both days.

`dbt build` runs models, data tests and unit tests together, so the existing CI
job covers all three layers.

The seed is destructive — it truncates `stg.*` and the rebuild truncates
`core.*` — so it aborts if `marts.pipeline_runs` already holds rows. Run it
only against an ephemeral database.

**Replay parity** — *is reprocessing the same batch safe?* This is the property
that makes an Airflow retry, a manual re-trigger, or a rerun after a partial
failure safe: all of them replay the same staging slice through
`db/pipeline_sql/10_rebuild_core.sql`. CI seeds staging, rebuilds, snapshots
core and all four marts into a `replay_check` schema, rebuilds a second time,
then requires `tests/fixtures/warehouse/assert_replay_parity.sql` to return zero
rows. It symmetric-differences both directions, so rows that *appeared* and rows
that *vanished* are each named, with explicit row-count guards because `EXCEPT`
is set-based and would not see a duplicated row.

**Failure diagnosis** — the four Tier-1 tests (both reconciliations, the mart
grain, and the roll-up invariant) set `store_failures=true`, so a red test
leaves its violating rows in `dbt_test__audit.<test_name>` instead of only a
count. This is deliberately *not* enabled on all 79 tests, which would clutter
the database for no diagnostic gain.

Note that `payment_reconciliation` compares per `(order_id, ingest_date)` — the
exact grain the payment aggregation groups by — rather than as one global `SUM`.
A global total passes whenever two errors cancel out (`-10` on one order, `+10`
on another), which is precisely the case a reconciliation test exists to catch.

**Static analysis** — SQLFluff runs in `ci-pr.yml` as a *correctness* gate, not
a formatter. The default rule set reports ~100 findings here, of which 96 are
pure layout (74 are 2-space vs 4-space indent alone); enforcing those would
reformat every model while catching no defect. `.sqlfluff` therefore enables
only the `AM*` ambiguity and `CV02`/`CV03` convention rules — implicit join
types, unknown result-column counts, ambiguous `ORDER BY` and `DISTINCT`. That
set found two real issues on adoption: an implicit `join` in
`v_reconcile_sales_daily` (now `inner join`) and a `select *` of unknown width
in the roll-up test. It uses the `jinja` templater rather than the `dbt` one, so
the linter is not coupled to either pinned dbt runtime.

**Mutation gate** — *do the layers above actually kill bugs?* Every layer here
asserts something; only the mutation gate proves those assertions have teeth. It
applies known-bad edits to the model SQL — `left join` → `inner join`, dropping
the `ingest_date` predicate, `COUNT(DISTINCT)` → `COUNT`, reversed
reconciliation arithmetic — and requires a named unit test to fail for each. See
[W3 — SQL mutation gate](W3-mutation-gate.md).

**Load recency** — *is the staging slice we are about to certify from recent
enough?* `db/init/008_stg_loaded_at.sql` adds
`loaded_at timestamptz not null default now()` to the four `stg.*` tables;
`sources.yml` declares `loaded_at_field: loaded_at` with `warn_after` and
`error_after` under `config:` on those four sources only; and
`warehouse_marts_validation` runs a distinct `check_source_freshness` task
upstream of the `dbt_warehouse` group, so the gate sits at the point of
consumption rather than immediately after the load, where it would be close to
tautological.

*Why not the columns already present.* `ingest_date` cannot serve: it is a CSV
column, named in `_copy_csv`'s explicit `COPY` column list, so its value is
whatever the input file says and it carries no relationship to load time.
`order_purchase_timestamp` cannot serve either — that is business event time,
which answers "what date does the newest record describe?", not "when did this
slice arrive?".

*What the signal actually is.* A **batch-load transaction timestamp**, not
literal row-arrival time. `now()` is transaction-start time, and
`load_raw_csv_to_stg` wraps the truncate and all four `COPY` calls in one
transaction, so one batch yields one identical value across all four sources by
construction rather than by coincidence — the four can never report inconsistent
freshness. `clock_timestamp()` would vary per row and is rejected.

*Rejected alternatives.* An audit-table-backed `loaded_at_query` — the audit
table does not exist, and the one arrival-shaped timestamp that does,
`marts.pipeline_runs.run_ts`, is written by the marts DAG *after* the step it
would guard, so gating on it is circular. Freshness inside the ingestion DAG —
it would catch staleness earlier but crosses the dbt ownership boundary this
document draws, and would need the dbt runtime in the ingestion image. A
standalone nightly job — ingestion is manual-trigger, so it would be permanently
red and get muted.

*The promise, exactly:*

> Prevent downstream certification from consuming staging whose most recent successful load is outside the permitted age.

This is **not**
an external arrival SLA and **not** missing-batch detection. The timestamp is
written by the load itself and the marts DAG is Asset-triggered by the same
pipeline, so if ingestion never runs the gate never evaluates. Real
missing-batch detection would need an independent expected-arrival schedule or
an upstream arrival signal, and is out of scope.

*What it does catch, all of which are real.* A marts re-trigger against a slice
loaded hours ago; an accidentally no-op or stale staging load; consumption after
abnormal orchestration delay; and a same-sized stale batch, which the exact-count
parity gate structurally cannot distinguish from today's.

*The migration's false-fresh window is accepted, not fixed.*
`add column ... not null default now()` assigns the evaluated default to
pre-existing rows, so immediately after the migration old staging rows report as
freshly loaded. Harmless here: the gate is only ever reached after
`load_raw_csv_to_stg` has truncated those rows, the window is one ingestion run
wide, and the failure mode is a false pass rather than a false failure. A
nullable transitional column or a sentinel timestamp would add permanent schema
complexity to guard a one-time state.

*Result status, not exit code.* Cosmos runs dbt in-process
(`InvocationMode.DBT_RUNNER`, because dbt-core is pinned into the Airflow
image's own Python), so `dbt_executable_path` is discarded and the Airflow
signal is `dbtRunnerResult.success`. The CLI's exit code 1 and that boolean come
from the same `FreshnessTask.interpret_results`, so the CI proof and the Airflow
runtime cannot diverge. Do not "fix" the gate by swapping `DBT_EXECUTABLE`.

*Two adjacent behaviours worth knowing.* A warn exits zero and gates nothing —
which is why `warn_error` must stay false and why no test asserts the warn
threshold. And an **empty** staging schema produces an error rather than a pass,
because a NULL `max(loaded_at)` maps to year 1; freshness must therefore never
run before the load or before the CI seed, and must never be added to the
mutation gate.

*Threshold basis — provisional and unmeasured.* The values
`warn_after: 30 minutes` / `error_after: 2 hours` are starting points. **No
measurement has been taken.** What would have to be measured is the elapsed time
from the **ingestion DagRun's end to the `check_source_freshness` TaskInstance's
start**, across several healthy Asset-triggered runs, with `warn_after` then set
with real margin above the observed spread. Note what is *not* the measurement
basis: `marts.pipeline_runs.run_ts` records when the marts audit wrote its row,
which is after the gate, and the marts DAG's own `dagrun_timeout=45 minutes` and
`validate_dbt_artifacts`'s `execution_timeout=40 minutes` are downstream budgets,
not arrival latencies. Those two timeouts are still worth knowing as risk
context — a 30-minute warn sits inside delay the pipeline already tolerates
elsewhere — but they cannot substitute for the measurement.

*Operational consequence.* A manual re-trigger of `warehouse_marts_validation`
more than `error_after` after ingestion will now fail. That is arguably correct —
marts should not be re-certified against a stale slice — but it changes operator
workflow: after redeploying dbt models, re-run ingestion rather than
re-triggering marts alone. An Airflow Param escape hatch was discussed and is
deliberately **not** part of this design; revisit only if the cost proves real.

## Schema naming is intentional

`macros/generate_schema_name.sql` returns the model's custom schema verbatim
and discards `target.schema`, which is the opposite of dbt's default
`<target_schema>_<custom_schema>` behaviour and its environment-isolation
advice. That is deliberate here: the marts must keep their legacy relation
names. `dags/warehouse_dbt.py` reads `marts.v_order_items_wide`,
`marts.v_sales_daily` and `marts.v_reconcile_sales_daily` by literal name in
the audit SQL, and publishes Assets whose URIs end in `marts/<view>`; the
Metabase and Superset models point at the same names. Restoring the default
prefix would rename every view and break the audit, the Assets and the BI
layer.

The trade-off is that this project has no per-developer schema isolation: two
targets pointed at the same database write the same `marts.*` relations. The
mitigation is that the project is only ever run against an ephemeral CI
database or the single local `dwh`.

After each successful build, Cosmos callbacks persist and the DAG validates:
`manifest.json`, `run_results.json`, `catalog.json`, and `index.html` under the
writable runtime sink `/tmp/warehouse_dbt_artifacts`, which also backs the Cosmos
warehouse docs endpoint.

## Reproduction

```powershell
Copy-Item dbt/warehouse/profiles.yml.example dbt/warehouse/profiles.yml
uv venv --python 3.12 .venv-dbt-warehouse
uv pip sync --python .venv-dbt-warehouse/Scripts/python.exe --require-hashes dbt/warehouse/requirements.txt
.venv-dbt-warehouse/Scripts/dbt.exe build --project-dir dbt/warehouse --profiles-dir dbt/warehouse
.venv-dbt-warehouse/Scripts/dbt.exe docs generate --project-dir dbt/warehouse --profiles-dir dbt/warehouse
```

The complete local-stack proof is:

```text
manual warehouse_orders_ingestion
  → successful core.orders Asset
  → warehouse_marts_validation (Cosmos WATCHER / dbt build)
  → dbt models and tests
  → validated artifacts
  → mart Assets + pipeline audit
```

The audit keeps the Airflow Asset-triggered DagRun ID in `run_id` and the
source ingestion DagRun ID in `ingestion_run_id`.
