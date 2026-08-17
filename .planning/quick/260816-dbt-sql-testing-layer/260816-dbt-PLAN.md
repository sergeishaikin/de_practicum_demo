---
gsd_plan_version: 1.0
task: dbt-sql-testing-layer
mode: quick
created: 2026-08-16
status: in-progress
---

# Quick Task — dbt/SQL testing layer for `dbt/warehouse`

Build a pragmatic, high-value testing layer for the SQL transformations in the
`warehouse_transform` dbt project. Verify existing coverage first; add only
what is genuinely missing.

## Verification findings (done before any implementation)

| Claim under test | Result | Evidence |
|---|---|---|
| dbt version supports unit tests | **Yes** | `dbt-core==1.12.2`, `dbt-postgres==1.11.0` (`dbt/warehouse/requirements.in`); unit tests GA since 1.8 |
| dbt version supports model contracts | **Yes** | same runtime |
| Tier-1 contracts are only *tagged*, not enforced | **False** | `models/marts/schema.yml` sets `config.contract.enforced: true` on all four models; `tests/test_warehouse_dbt.py::test_quality_contracts_and_selectors_are_present` asserts `enforced: true` appears 4× |
| Grain/uniqueness tests missing | **False** | `core.orders.order_id` has `unique`+`not_null`; `core.order_items` has `core_order_items_grain_unique`; `tests/order_items_wide_grain.sql` checks the mart grain |
| Row-count invariant needed to catch join multiplication | **Redundant** | `core.orders.order_id` unique + mart grain test already make fan-out detectable; a count-equality test adds no new failure mode |
| `generate_schema_name` is an environment-isolation defect | **Intentional here** | Models set `+schema: marts`; the Airflow audit in `dags/warehouse_dbt.py` reads `marts.v_order_items_wide` / `marts.v_sales_daily` / `marts.v_reconcile_sales_daily` by literal name, and `MART_ASSETS` URIs are `.../marts/<view>`. Stripping `target.schema` is what preserves the legacy relation names (`docs/warehouse/W1-dbt-ownership.md`). Document, do not change. |
| Reconciliation / payment tests already cover the proposed cases | **Partly** | They assert production *data* reconciles; none of them exercise the *SQL logic* (FULL JOIN, COALESCE, `ingest_date` join, LEFT JOIN preservation) against controlled inputs |
| dbt unit tests would run in CI | **Yes, for free** | `ci-pr.yml` job `warehouse-dbt-contract` runs `dbt build`, which executes unit tests |
| SQL linting exists | **No** | no sqlfluff config anywhere in the repo |
| Source freshness configured | **No** | and not meaningful: `stg.*` has no `loaded_at_field`, and ingestion is manual-trigger by design |

**Net gap:** zero unit tests. Every existing check is a data test that needs a
built warehouse and real rows; none of them pin the transformation semantics.

## Scope

### P0
1. Unit tests for `v_reconcile_sales_daily` — equal, mismatch, mart-only date,
   source-only date (FULL JOIN + COALESCE), and cross-batch `ingest_date`
   exclusion.
2. Unit tests for `v_order_items_wide` — LEFT JOIN preserves unmatched items,
   enrichment of matched items, multiple items per order, NULL payment fields.
3. Grain/uniqueness: **already covered** — add nothing.

### P1
4. Unit test for `v_sales_daily` — `count(distinct order_id)` vs `count(*)`,
   gross/freight sums, multiple dates.
5. Contracts: **already enforced** — add nothing.
6. Deterministic integration fixture: staging → core → marts → reconciliation,
   asserting final aggregates and `diff_amount = 0`.
7. Cross-model invariant: `v_customer_state_daily` totals roll up to
   `v_sales_daily` (the one invariant not implied by an existing test).

### Deliberately out of scope
- sqlfluff (new toolchain + lock churn; no defect it would have caught here).
- Source freshness (no `loaded_at_field`; manual-trigger ingestion by design).
- Changing `generate_schema_name` (would break the Airflow audit and Assets).
- Row-count equality invariant on `v_order_items_wide` (redundant).
- Unit-testing `v_customer_state_daily` in isolation (tier-2; its logic is
  `v_sales_daily` plus one grouping key, and the roll-up invariant covers it).

## Verification
- `dbt parse` + `dbt test --select test_type:unit` against the local Postgres.
- `pytest tests/test_warehouse_dbt.py`.
- Fast repo suite.
