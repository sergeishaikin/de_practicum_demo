---
phase: 3
slug: staging-source-freshness-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-17
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `03-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x via `uv run --locked`; pytest-bdd for `tests/features/` |
| **Config file** | `pytest.ini` — `testpaths = tests`, `addopts = -m "not integration and not e2e and not airflow"` |
| **Quick run command** | `uv run --locked pytest -q tests/test_warehouse_dbt.py tests/test_h1_runtime.py` |
| **Full suite command** | `uv run --locked pytest` |
| **Estimated runtime** | quick ~2 s · full ~60 s |
| **Live DagBag layer** | `uv run --locked pytest tests/test_dags.py -m airflow` (needs `de-demo-airflow`) |
| **BDD layer** | `uv run --locked pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"` |
| **dbt runtime** | `.venv-dbt-warehouse/Scripts/dbt.exe` — **never bare `dbt`** |

---

## Sampling Rate

- **After every task commit:** `uv run --locked ruff check . && uv run --locked black --check . && uv run --locked pytest -q tests/test_warehouse_dbt.py tests/test_h1_runtime.py`
- **After every DAG-touching commit, additionally:** `uv run --locked ruff check dags --select AIR3 --preview`
- **After every plan wave:** `uv run --locked pytest` (full fast suite incl. the `--cov=iceberg` gate)
- **Before `/gsd-verify-work`:** full suite green; live layer green if the stack is available
- **Max feedback latency:** ~5 s for the quick command

---

## Per-Task Verification Map

Task IDs are assigned at planning time; this map is requirement-keyed and the
planner must bind each task to a row.

| Req | Behaviour | Test Type | Automated Command | Exists |
|-----|-----------|-----------|-------------------|--------|
| R1 | Fresh staging → freshness passes | live integration | new `ci-pr.yml` step after the seed | ❌ new |
| R1c | Workflow contains the fresh-pass step | static | `pytest -q tests/test_warehouse_dbt.py` | ❌ new |
| R2 | Stale beyond `error_after` → freshness fails | live integration | new `ci-pr.yml` step, `if <cmd>; then exit 1; fi` idiom | ❌ new |
| R2b | …and blocks dbt build + mart publication | BDD, faked DB | `pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"` | ❌ new scenario |
| R2c | `check_source_freshness` upstream of `dbt_producer_watcher` | DagBag structure | `pytest tests/test_dags.py -m airflow` | ❌ new assertion |
| R2d | DAG wires the gate and imports from `cosmos.operators.local` | static | `pytest -q tests/test_warehouse_dbt.py` | ❌ new |
| R3 | All four staging tables share one `loaded_at` | live integration | fixture assertion, zero-rows-is-pass convention | ❌ new |
| R3b | Truncate + four copies stay in one transaction | BDD | existing scenario *"Staging load truncates before every batch…"* | ✅ must stay green |
| R4 | Staging row-count validation intact | BDD | existing scenarios `.feature:18-31` | ✅ unchanged |
| R5 | Core/mart publication fail-closed intact | BDD | existing scenarios `.feature:38-77` | ✅ unchanged |
| R6 | Migration `008` is additive, idempotent, replayed | static contract | `pytest -q tests/test_h1_runtime.py` | ❌ new |
| R6b | Applying `008` twice is a no-op | live | `ci-h1-clean.yml` already double-applies via bootstrap | ✅ implicit |
| R7 | `core.*` declares no freshness | static contract | `pytest -q tests/test_warehouse_dbt.py` | ❌ new |
| R8 | SQL style | static | `sqlfluff lint dbt/warehouse/models dbt/warehouse/tests dbt/models` | ✅ existing |
| R9 | dbt project still parses | live | `ci-pr.yml` `dbt parse` | ✅ existing |
| R10 | 9 dbt unit tests unaffected | live | `ci-pr.yml` `dbt build` | ✅ must stay green |
| R11 | Mutation gate unaffected | live | `ci-pr.yml` mutation step | ✅ must stay green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/fixtures/warehouse/backdate_staging_loaded_at.sql` — R2
- [ ] `tests/fixtures/warehouse/reset_staging_loaded_at.sql` — R2
- [ ] R3 assertion — appended to `assert_marts.sql` or a new `assert_loaded_at_is_one_batch.sql`
- [ ] New contract tests in `tests/test_warehouse_dbt.py` — R1c, R2d, R7
- [ ] New migration/bootstrap contract test in `tests/test_h1_runtime.py` — R6
- [ ] New DagBag assertion in `tests/test_dags.py` — R2c, **written after observing the real task mapping, not guessed**
- [ ] New Gherkin scenario + steps — R2b
- [ ] Two new CI steps + one `if: always()` reset — R1, R2

No framework install needed; every layer already exists.

---

## Manual-Only Verifications

| Behaviour | Requirement | Why Manual | Test Instructions |
|-----------|-------------|------------|-------------------|
| Healthy ingestion→marts delay | threshold basis | Requires live Asset-triggered runs; excluded by the stateful boundary unless explicitly authorised | Trigger `warehouse_orders_ingestion`, record elapsed time from its completion to the `check_source_freshness` task start, across several healthy runs. Set `warn_after` with margin above the observed spread and record the basis in W1. |

**If the measurement is not performed, W1 must state the thresholds are
provisional and unmeasured — verbatim, not implied.**

---

## Known Risks Carried From Research

- **A1** — the exact task set `freshness_task >> dbt_group` produces depends on
  Cosmos internals that could not be fully confirmed offline. The
  `tests/test_dags.py` assertion must be written after observing the real
  DagBag mapping.
- An **empty** staging table produces a freshness *error*, not a pass
  (`NULL max_loaded_at` → year 1). Benign here because the existing parity gate
  already rejects empty staging, but it must not surprise anyone later.
- `sqlfluff` lints only `dbt/warehouse/models`, `dbt/warehouse/tests`, `dbt/models`.
  `db/init/008_*.sql` and new fixture SQL are deliberately **not** linted — do
  not widen the lint scope.

---

## Validation Sign-Off

- [ ] All tasks bound to a requirement row above
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s for the quick command
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
