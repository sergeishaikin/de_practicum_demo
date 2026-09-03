# W4 — dbt architecture gate

The other warehouse gates ask whether the SQL is *correct*. This one asks a
question none of them can: *does the dependency graph still obey the layering we
chose?* A model can compute exactly the right number, pass every contract and
survive every mutation while reading a raw source directly — and that defect is
invisible to all of them, because nothing is wrong with the arithmetic.

## Scope

This document covers `dbt/warehouse` only. The `dbt/` semantic project
(`lakehouse_semantic`, Trino) has not adopted the gate and is not governed by the
policy here; whether it should is an open question, not a decision this document
records. Nothing below should be read as repository-wide dbt policy.

## The rule it enforces

Raw relations are reached by exactly one layer, and everything downstream goes
through `ref()`:

```text
source('core', ...)              source('staging', ...)
        ↓                                ↓
   stg_core__*                     stg_staging__*
        ↓                                ↓
    marts.v_*                    v_reconcile_sales_daily
        └────────────────────────────────┘
```

The dbt staging models are deliberately thin — a column projection and nothing
else. No joins, no aggregates, no filters. Business logic stays in the marts,
which is why the `LEFT JOIN` in `v_order_items_wide` was *not* pushed down: it is
a business decision about orphaned items, and it is pinned by a unit test and a
mutation (see [W3](W3-mutation-gate.md)).

Two things named "staging" now exist and they are not the same thing:

| Relation | Owner | Meaning |
|---|---|---|
| `stg.*` | Airflow ingestion | the physical arrival point for one CSV batch |
| `staging.stg_*` | dbt | the normalization boundary between sources and marts |

## What it found

The gate was adopted against the project as it stood, with no rules relaxed to
make it pass. Every error was a real layering violation:

| Rule | Count | What it caught |
|---|---|---|
| `source-in-downstream` | 4 | all four marts read `{{ source() }}` directly |
| `multiple-sources-joined` | 2 | two marts joined two raw sources to each other |
| `direct-source-and-ref` | 1 | `v_reconcile_sales_daily` mixed `source()` and `ref()` |

Seven errors, but **one cause**: the project had no staging layer at all. Adding
it cleared all three rules at once.

```text
before   errors 7   warnings 4
after    errors 0   warnings 2
```

**The acceptance criterion is `errorCount = 0`.** The tool also prints a 0–100
score, and it is not the gate. Score moves when the rule set changes, when a
finding is spread across more or fewer files, or when a new rule ships in a
future version — none of which are statements about this project's architecture.
Do not put a score threshold in CI and do not report the score as a quality
metric.

## The two warnings that stay

Both are `source-childs`, and both are deliberate.

**`staging.order_payments`** is the interesting one. The rule counts *downstream
models*, and this source has none — but it is read directly by
`tests/payment_reconciliation.sql`, a singular test, which is not a model. So the
warning is accurate about the graph and wrong about the conclusion:

```text
no downstream model  ≠  unused source
```

Deleting the declaration to clear the warning would break the reconciliation
test at compile time. This is an accepted limitation of how the rule sees the
graph, not a suppression.

**`staging.customers`** genuinely has no dbt consumer today. It stays declared
because the four `stg.*` tables are one ingestion contract — the freshness gate
in [W1](W1-dbt-ownership.md) asserts thresholds on all four, and the repository
contracts require all four declarations. Removing one to satisfy a linter would
weaken a gate that exists for a stronger reason.

Do **not** add `rules.dbt-doctor/source-childs=off`. The rule is useful; two
known, explained warnings are cheaper than losing it everywhere. A visible
warning with a written reason is a better artifact than a silent exception.

## The two rules that are off

`dbt/warehouse/.dbt-doctor`:

```text
preset=default
fail_on=error

rules.dbt-doctor/marts-prefix=off
rules.dbt-doctor/exposure-parents-materializations=off
```

**`marts-prefix`** wants `fct_` / `dim_` / `rpt_` prefixes. The mart views keep
their existing public names (`v_sales_daily` and the rest) because
`dags/warehouse_dbt.py` reads them by literal `marts.*` name and publishes Assets
under `marts/<view>` URIs. This is a policy mismatch with a generic convention,
not deferred debt.

**`exposure-parents-materializations`** warns that an exposure depends on a view
rather than a table. Views are the intended materialization here; the marts are
thin projections over `core.*` and materializing tables to satisfy a generic
performance heuristic would add a refresh contract nobody asked for.

Both are off because they were considered and rejected, which is the reason this
section exists — otherwise the next person reads two `off` lines as laziness.

## Operational contract

The gate runs `dbt-doctor@0.3.4`, pinned. `@latest` would let the gate change
under a PR that did not touch dbt.

**Fresh manifest, asserted on the file.** The DAG rules read
`target/manifest.json`, so a stale artifact gates the wrong graph. The invariant
is deliberately *not* "the `target/` directory was deleted":

```bash
rm -f target/manifest.json
dbt parse
test -s target/manifest.json
```

On Windows a locked handle can leave `target/` undeletable while its contents are
already gone, so a recursive delete is an unreliable precondition on a
cross-platform toolchain. Asserting that the manifest is absent, that `parse`
succeeded, and that a new manifest exists proves what actually matters.

**Never pass `--score` to the blocking invocation.** In the pinned 0.3.4 runtime,
`--score --fail-on error` was observed to exit 0 on a project with four errors.
Scoring, if ever wanted, belongs in a separate non-blocking call.

**Rule overrides need the `dbt-doctor/` namespace.** In this pinned runtime,
`rules.dbt-doctor/marts-prefix=off` was verified to work while
`rules.marts-prefix=off` and `ignore.rules=marts-prefix` were silently ignored —
no error, no warning, the rule simply stayed on. Some documentation examples show
unqualified IDs; on 0.3.4 the qualified form is the one that takes effect. A
config change here must be verified by observing the finding disappear, not by
the run exiting 0.

**Pass the manifest as a flag, not a config key.** CI uses
`--manifest target/manifest.json`. The documented `manifest_path=` config key was
never exercised on this project, and after the namespace discrepancy above an
unverified implicit setting is not something to put in a blocking gate.

**Offline.** CI passes `--offline`. Nothing about the project — name, score,
issue counts — needs to reach the sharing service for the gate to do its job.

**PR mode versus push mode.** `ci-pr.yml` scans changed models against the
actual base branch on a pull request and the whole project otherwise:

```text
pull_request   fresh manifest + --diff origin/<base_ref>
push           fresh manifest + full scan
```

That is why this job alone checks out with `fetch-depth: 0` — `--diff` resolves
the base ref locally, and the shallow default leaves it with nothing to compare
against. Hardcoding `--diff main` would gate the wrong base on any PR that does
not target `main`.

## Running it locally

No database needed; the gate is static.

```powershell
cd dbt\warehouse
Remove-Item .\target\manifest.json -Force -ErrorAction SilentlyContinue
..\..\.venv-dbt-warehouse\Scripts\dbt.exe parse --profiles-dir .
npx -y dbt-doctor@0.3.4 --offline --manifest target/manifest.json
```

Expected:

```text
exit 0
errors 0
source-childs warnings 2
```

Use the project venv, never a bare `dbt` — see the note in
[TESTING.md](../TESTING.md#warehouse-dbt).

## Upgrading

The pin exists because two of the behaviours above were established by
experiment, not read from documentation, and neither is guaranteed to survive a
release. Treat an upgrade as a change to the gate itself:

1. Bump the version in `ci-pr.yml` and in [TESTING.md](../TESTING.md#warehouse-dbt).
2. Re-verify the rule namespace by observing a finding *disappear* — set
   `rules.marts-prefix=off` (unqualified) and confirm `marts-prefix` still fires.
   If it stops firing, the unqualified form now works and this document is stale.
3. Re-verify the `--score` interaction on a project with a known error; if
   `--score --fail-on error` still exits 0, keep the prohibition.
4. Re-run the gate on `warehouse_transform` and diff the findings against the
   accepted state in [the two warnings that stay](#the-two-warnings-that-stay).
   New errors are a decision, not a formality: either the
   code changes or the rule is turned off with a reason written here.

A version bump that only makes CI green again, without steps 2–4, silently
replaces a verified gate with an unverified one.

## Limits

The gate reasons about the graph, never about data. It cannot tell a correct
number from a wrong one, and a project with zero errors can still publish
nonsense. It also does not replace SQLFluff, which asks whether an individual
statement is unambiguous; the two rarely fire on the same defect. What each layer
does and does not prove is in [W1](W1-dbt-ownership.md#testing-layers).
