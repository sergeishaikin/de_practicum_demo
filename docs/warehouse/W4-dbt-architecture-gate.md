# W4 — dbt architecture gate

The other warehouse gates ask if the SQL is correct. This gate asks a different
question: does the dependency graph obey the layer rule?

A model can calculate the correct number, satisfy every contract and survive
every mutation, and still read a raw source directly. The other gates cannot see
that defect, because the arithmetic is correct.

## Scope

This document applies to `dbt/warehouse` only.

The `dbt/` semantic project (`lakehouse_semantic`, Trino) does not use the gate.
Whether the semantic project must use the gate is an open question. This document
does not decide it. Do not read this document as a policy for all dbt projects in
the repository.

## Rule

Mart models must not call `source()`.

Only dbt staging models can call `source()`. Mart models must read a dbt staging
model with `ref()`.

```text
source('core', ...)              source('staging', ...)
        ↓                                ↓
   stg_core__*                     stg_staging__*
        ↓                                ↓
    marts.v_*                    v_reconcile_sales_daily
        └────────────────────────────────┘
```

A dbt staging model must contain a column projection only. Do not put a join, an
aggregate or a filter in a dbt staging model. Keep business logic in the mart
models.

The `LEFT JOIN` in `v_order_items_wide` stays in the mart for that reason. The
join decides what happens to an order item that has no order header, so the join
is business logic. A unit test and a mutation protect the join. See
[W3](W3-mutation-gate.md).

## Layer ownership

Two layers have the name "staging". They are different layers.

| Relation | Owner | Meaning |
|---|---|---|
| `stg.*` | Airflow | the physical arrival point for one CSV batch |
| `staging.stg_*` | dbt | the dbt staging models that read the raw relations |

Write `stg.*` for the Airflow layer. Write `dbt staging model` for the dbt layer.
Do not use another name for either layer.

## What the gate found

The project adopted the gate with no rule relaxed. Every error was a real
violation of the rule:

| Rule | Count | What it caught |
|---|---|---|
| `source-in-downstream` | 4 | all four mart models called `source()` |
| `multiple-sources-joined` | 2 | two mart models joined two raw sources |
| `direct-source-and-ref` | 1 | `v_reconcile_sales_daily` called `source()` and `ref()` |

Seven errors, but one cause: the project had no dbt staging model. Four new dbt
staging models cleared all three rules.

```text
before   errors 7   warnings 4
after    errors 0   warnings 2
```

## Pass criterion

The gate passes when `errorCount` is 0.

```text
blocking      errorCount = 0
not blocking  score, warningCount
```

dbt Doctor also prints a score from 0 to 100. The score is not the gate. The
score changes when the rule set changes, when a finding moves between files, and
when a new version adds a rule. None of those changes describe this project.

Do not add a score threshold to CI. Do not report the score as a quality
measurement. Do not change the model design only to increase the score.

## Accepted warnings

Two `source-childs` warnings remain. Keep both.

`source-childs` reads the dbt model graph only. It does not see a consumer that
lives outside that graph, and both sources have one:

| Source | Consumers | Downstream dbt model |
|---|---|---|
| `staging.order_payments` | the Airflow core rebuild; a dbt singular test | none |
| `staging.customers` | the Airflow core rebuild; the freshness contract | none |

`db/pipeline_sql/10_rebuild_core.sql` reads `stg.order_payments` to aggregate the
payment columns, and joins `stg.customers` to attach `customer_state`. That file
is Airflow-owned SQL, so no dbt model depends on either source. The warning
describes the dbt graph correctly and supports the wrong conclusion:

```text
no downstream dbt model  ≠  unused source
```

**`staging.order_payments`.** `tests/payment_reconciliation.sql` also reads the
source directly, and a singular test is not a model. If you delete the
declaration, that test fails to compile. Keep the declaration.

**`staging.customers`.** The four `stg.*` tables are one ingestion contract: the
freshness gate in [W1](W1-dbt-ownership.md) asserts thresholds on all four
tables, and the repository contracts require all four declarations.

Do not add `rules.dbt-doctor/source-childs=off`. The rule is useful elsewhere.
Two explained warnings cost less than the loss of the rule. Do not create an
empty model to remove a warning.

## Disabled rules

`dbt/warehouse/.dbt-doctor`:

```text
preset=default
fail_on=error

rules.dbt-doctor/marts-prefix=off
rules.dbt-doctor/exposure-parents-materializations=off
```

We disable these two rules on purpose. The rules do not match this project
design. Do not disable another rule only to make CI pass.

**`marts-prefix`** requires a `fct_`, `dim_` or `rpt_` prefix. The mart models
keep their public names, such as `v_sales_daily`. `dags/warehouse_dbt.py` reads
those names literally and publishes Assets under `marts/<view>`. A rename breaks
the DAG.

**`exposure-parents-materializations`** warns when an exposure depends on a view.
The mart models are views on purpose. The mart models are thin projections over
`core.*`. A table would add a refresh contract that this project does not need.

## Procedure: run the gate locally

The gate is static. You do not need a database. `dbt parse` does not connect to
PostgreSQL.

1. Delete the old manifest.
2. Run `dbt parse` from the project venv.
3. Check that the new manifest exists.
4. Run dbt Doctor and pass the manifest.

```powershell
cd dbt\warehouse
Remove-Item .\target\manifest.json -Force -ErrorAction SilentlyContinue
..\..\.venv-dbt-warehouse\Scripts\dbt.exe parse --profiles-dir .
npx -y dbt-doctor@0.3.4 --offline --manifest target/manifest.json
```

Expected result:

```text
exit     0
errors   0
warnings 2   (source-childs, see Accepted warnings)
```

Do not use a bare `dbt`. Use the project venv. See
[TESTING.md](../TESTING.md#warehouse-dbt).

## CI behaviour

`ci-pr.yml` runs the gate in the `warehouse-dbt-contract` job, after the
freshness steps and before `dbt build`.

| Event | Gate command |
|---|---|
| `pull_request` | fresh manifest, then `--diff origin/<base_ref>` |
| push | fresh manifest, then a full scan |

The job checks out with `fetch-depth: 0`. dbt Doctor resolves the base branch
locally, so a shallow checkout gives dbt Doctor nothing to compare. Do not write
`--diff main`. A pull request that targets another branch would then compare
against the wrong base.

CI passes `--offline`. The gate does not need the sharing service. No project
data must reach a remote service for the gate to work.

## Version 0.3.4 behaviour

CI pins `dbt-doctor@0.3.4`. Do not use `@latest`. A new version must not change
the gate under a pull request that does not touch dbt.

We established the three items below by experiment on version 0.3.4. Do not
assume that a later version behaves the same way.

**Rule overrides need the `dbt-doctor/` namespace.**

```text
works              rules.dbt-doctor/marts-prefix=off
silently ignored   rules.marts-prefix=off
silently ignored   ignore.rules=marts-prefix
```

The ignored forms produce no error and no warning. The rule stays on. Some
documentation examples show the unqualified form. After you change the rule
configuration, confirm that the finding disappears. Do not accept exit 0 as
proof.

**Do not pass `--score` to the blocking command.** On version 0.3.4,
`--score --fail-on error` returned exit 0 on a project with four errors. Use
`--score` only in a separate command that does not block the build.

**Pass the manifest as a flag.** CI uses `--manifest target/manifest.json`. This
project never tested the `manifest_path=` config key. Do not put an untested
implicit setting in a blocking gate.

## Procedure: keep the manifest fresh

dbt Doctor reads `target/manifest.json`. An old manifest describes an old graph,
so the gate would check the wrong graph.

The invariant is:

```text
old manifest deleted
+ dbt parse succeeded
+ new manifest exists
```

The invariant is **not** "the `target/` directory was deleted". On Windows, a
locked handle can keep the directory after its contents are gone, so a recursive
delete is an unreliable precondition. Assert on the manifest file:

```bash
rm -f target/manifest.json
dbt parse
test -s target/manifest.json
```

## Procedure: upgrade dbt Doctor

An upgrade changes the gate. Treat an upgrade as a change, not as maintenance.

1. Change the version in `ci-pr.yml` and in
   [TESTING.md](../TESTING.md#warehouse-dbt).
2. Test the rule namespace. Set `rules.marts-prefix=off` without the namespace.
   If `marts-prefix` still fires, keep the namespace and keep this document. If
   `marts-prefix` stops firing, the unqualified form now works and this document
   is out of date.
3. Test `--score` on a project with a known error. If `--score --fail-on error`
   still returns exit 0, keep the prohibition.
4. Run the gate on `warehouse_transform`. Compare the findings against
   [Accepted warnings](#accepted-warnings). A new error is a decision: change the
   code, or disable the rule and write the reason in this document.

If you change the version and skip steps 2, 3 and 4, you replace a tested gate
with an untested gate.

## Limits

The gate reads the graph. The gate does not read data. A project with zero errors
can still publish wrong numbers.

The gate does not replace SQLFluff. SQLFluff asks if one statement is
unambiguous. The two tools rarely report the same defect. For what each test
layer proves, see [W1](W1-dbt-ownership.md#testing-layers).
