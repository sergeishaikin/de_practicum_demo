# W3 — SQL mutation gate

Ordinary tests answer *"does the SQL behave correctly today?"*. The mutation gate
answers the stronger question: *"would the suite notice if the SQL became subtly
wrong?"* It lets the project make a claim that a passing test count cannot:

> All tests pass, **and** the known SQL defects we care about cannot survive them.

## How it runs

`scripts/mutation_test.py` copies `dbt/warehouse` to a temporary directory,
applies one mutation to the copy, and runs the single unit test expected to fail.
Production SQL is never modified — the copy is removed in a `finally` block, so a
crashed dbt run cannot leave a mutated model behind. `ci-pr.yml` runs the gate in
the `warehouse-dbt-contract` job and uploads `mutation-report.json`.

Each mutation runs only its narrowest killer test, never the full 88-check suite:
the whole gate is ~8 dbt invocations and is dominated by dbt start-up, not by the
tests themselves.

## The catalogue

| Mutation | Model | Killed by | Guards against |
|---|---|---|---|
| `left_join_to_inner_join` | `v_order_items_wide` | `order_items_wide_keeps_items_without_a_matching_order` | items whose header is missing are silently dropped |
| `full_join_to_left_join` | `v_reconcile_sales_daily` | `reconcile_sales_daily_reports_both_sides_of_the_full_join` | source-only days hidden, so unreconciled data reads as reconciled |
| `drop_ingest_date_predicate` | `v_reconcile_sales_daily` | `reconcile_sales_daily_ignores_cross_batch_ingest_dates` | items from one batch reconcile against another batch's headers |
| `count_distinct_to_count` | `v_sales_daily` | `sales_daily_counts_orders_distinctly_and_sums_money_per_day` | `orders_cnt` counts line items, inflating every daily figure |
| `reverse_reconciliation_arithmetic` | `v_reconcile_sales_daily` | `reconcile_sales_daily_reports_both_sides_of_the_full_join` | `diff_amount` reports the wrong sign, inverting every verdict |
| `drop_coalesce_on_mart_side` | `v_reconcile_sales_daily` | `reconcile_sales_daily_reports_both_sides_of_the_full_join` | a source-only day reports NULL instead of 0 |
| `sum_wrong_money_column` | `v_sales_daily` | `sales_daily_counts_orders_distinctly_and_sums_money_per_day` | gross sales reports freight — plausible, and wrong |
| `state_count_distinct_to_count` | `v_customer_state_daily` | `customer_state_daily_partitions_each_day_by_state` | per-state counts double-count multi-item orders |

Current result: **8 mutations, 8 killed, 0 survived, 0 invalid, 0 errors.**

## Classification

| Status | Meaning | CI |
|---|---|---|
| `killed` | the intended test failed — the mutation is covered | pass |
| `survived` | every selected test still passed — the defect could ship | **fail** |
| `invalid` | the mutated SQL no longer compiles, so it exercised nothing | not counted as coverage |
| `equivalent` | behaviour genuinely unchanged; documented rather than forced | not counted as coverage |
| `error` | the pattern no longer matches, or the selector resolved to nothing | **fail** |

`invalid` and `error` are kept distinct on purpose. A mutation that stops the
project compiling proves nothing about the tests, and a mutation whose `find`
pattern has drifted would otherwise quietly reduce coverage while the killed
count still looked healthy. `tests/test_mutation_harness.py` guards that in the
fast suite: it asserts every pattern still matches its model exactly once, and
that every `killer` names a unit test that actually exists.

## The self-test

A gate that cannot see a survivor is worthless, so the harness carries one
mutation that is *expected* to survive: `selftest_order_status_from_header` takes
`order_status` from the order header instead of the line item. That is a real
semantic change, but no unit test asserts that column, so it survives — and the
integration self-test requires the harness to report exactly that, then requires
the gate to exit 1 when the same mutation is declared as one that must die.

It is deliberately excluded from `CATALOGUE`, since including it would fail CI
permanently over a known, documented gap. It also names a genuine (small) hole:
if `order_status` provenance ever matters, that is the test to add.

## Adding a mutation

When a regression class is discovered, append a `Mutation` to `CATALOGUE` in
`scripts/mutation_test.py`:

```python
Mutation(
    name="stable_identifier",
    path="models/marts/<model>.sql",
    find="<exact, unique substring>",
    into="<the wrong version>",
    killer="<narrowest unit test expected to fail>",
    rationale="<the defect this would ship>",
)
```

`find` must match exactly once — the harness raises rather than guessing, and the
fast catalogue test fails if it ever stops matching. Prefer the narrowest killer:
the gate deliberately never runs the full suite.

Run locally with:

```powershell
python scripts/mutation_test.py --self-test --json mutation-report.json
```

## Limits

The gate proves the suite catches *these* defects; it is not a coverage
percentage and makes no claim about defects nobody has thought of. It also says
nothing about the shape of the graph. [W4](W4-dbt-architecture-gate.md) enforces
the layer rule separately. It runs only
against Tier-1 mart SQL — the semantic models are thin aliases (see
`W1-dbt-ownership.md`), and the staging-to-core rebuild is guarded by replay
parity instead (`W2-execution-contract.md`).
