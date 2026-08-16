---
gsd_summary_version: 1.0
task: dbt-sql-testing-layer
mode: quick
status: complete
completed: 2026-08-16
---

# Summary — dbt/SQL testing layer for `dbt/warehouse`

## What changed

| File | Change |
|---|---|
| `dbt/warehouse/models/marts/unit_tests.yml` | new — 5 fixture-driven unit tests |
| `dbt/warehouse/tests/customer_state_rolls_up_to_sales_daily.sql` | new — cross-model roll-up invariant |
| `tests/fixtures/warehouse/seed_staging.sql` | new — deterministic staging seed, guarded against real warehouses |
| `tests/fixtures/warehouse/assert_marts.sql` | new — exact expectations for core + all four marts, zero rows = pass |
| `.github/workflows/ci-pr.yml` | integration step now seeds staging and runs the production `10_rebuild_core.sql` instead of hand-writing `core.*`, then asserts the expectations |
| `tests/test_warehouse_dbt.py` | two repository contracts keeping the unit tests and the fixture honest |
| `docs/warehouse/W1-dbt-ownership.md` | testing-layer documentation and the `generate_schema_name` rationale |

## Not added, and why

- **Grain/uniqueness tests** — already present (`core.orders.order_id` unique,
  `core_order_items_grain_unique`, `tests/order_items_wide_grain.sql`).
- **Model contracts** — already `enforced: true` on all four models.
- **Row-count equality invariant on `v_order_items_wide`** — redundant given the
  above; adds no distinct failure mode.
- **sqlfluff** — new toolchain and lock churn, no defect here it would catch.
- **Source freshness** — `stg.*` has no `loaded_at_field`; ingestion is
  manual-trigger by design.
- **`generate_schema_name` change** — intentional; documented instead. The
  Airflow audit and Asset URIs depend on the literal `marts.*` names.
- **Isolated unit test for `v_customer_state_daily`** — tier-2, and its logic is
  `v_sales_daily` plus one grouping key, covered by the roll-up invariant.

## Verification evidence

| Check | Result |
|---|---|
| `dbt parse` | clean |
| `dbt test --select test_type:unit` | PASS=5 ERROR=0 in 1.43s |
| Mutation check: `LEFT JOIN` → `JOIN` | ERROR=1 (caught) |
| Mutation check: drop `ingest_date` predicate | ERROR=1 (caught) |
| Mutation check: `FULL JOIN` → `LEFT JOIN` | ERROR=1 (caught) |
| Mutation check: `count(distinct)` → `count` | ERROR=1 (caught) |
| Full `dbt build` on a throwaway `dwh_fixture_check` database | PASS=27 ERROR=0 in 2.76s |
| `assert_marts.sql` on the fixture | zero rows; `diff_amount = 0.00` on both days |
| `assert_marts.sql` after a +5.00 price mutation | 8 violation rows with exact diffs |
| Seed guard against a non-empty `marts.pipeline_runs` | aborts, exit 3, staging intact |
| `ruff check .` / `black --check .` | clean |
| `pytest` | 231 passed, 54 deselected |
| Live `dwh` after the run | untouched — 8 pipeline runs, 1000 stg orders, 1149 core items |

## Environment note

The local Docker VM disk was 100% full (1007 GB, 0 free), which had
`de-demo-postgres` in a crash loop (`PANIC: ... No space left on device`).
With the user's approval, `docker builder prune -af` (15.94 GB) and
`docker image prune -a -f` (3.95 GB) reclaimed ~19.9 GB; Postgres recovered to
healthy. Named volumes were not touched. The VM is still at 98%.
