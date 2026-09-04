---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 03
subsystem: observability
tags: [medallion, metrics, telemetry, iceberg, snapshots, testing]

requires:
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 02
    provides: the cycle/phase columns, PHASES closed set and cycle-only Prometheus guard this plan populates
provides:
  - One cycle_id per run(), threaded through _run_m4 / _run_legacy / run_b2
  - Four phase records per b2+shadow cycle (b2, shadow, gold, cycle) with cycle written last
  - Mutually non-overlapping phase durations, with the writer's state-load preamble attributed to no phase
  - B2Outcome physical-cost roll-up onto the cycle record
  - Bronze / Silver / Gold snapshot identities on the rows where they are meaningful
  - FakeMetrics.cycles() for scenarios that legitimately run more than one cycle
affects: [04-04 harness liveness marker, 04-05 Gold skip, 04-06 shadow certificate, 04-07 documentation contract]

tech-stack:
  added: []
  patterns:
    - "One run identity generated with uuid.uuid4().hex and threaded down, following the writer's load_id precedent"
    - "Phase segmentation by subtraction, with the unattributed residual named in a comment"

key-files:
  created: []
  modified:
    - iceberg/medallion/iceberg_medallion.py
    - tests/test_m4_gold.py
    - tests/test_b2_medallion.py
    - tests/test_medallion.py
    - tests/features/test_shadow_cutover.py
    - tests/support/fakes.py

key-decisions:
  - "`silver_duration_ms` and `gold_duration_ms` stay populated only on the `cycle` row, keeping today's inclusive meaning, so historical rows remain byte-for-byte interpretable and `cycle_id IS NULL` cleanly separates the two eras. Those two columns are never reused for a phase-scoped value."
  - "The shadow segment is the whole pre-Gold window minus the incremental writer's own window. Because run_b2 starts its timer only after loading progress, the outbox listing and the completion ledger, b2 + shadow + gold is less than or equal to the cycle; the residual is the writer's state-load preamble and is deliberately attributed to no phase, with a comment at the subtraction saying so."
  - "The `shadow_failed` record carries `phase=\"cycle\"` — it is an outer cycle that aborted before Gold, not a nested phase that failed."
  - "A `None` return from `run_b2` means \"no physical cost measured\", never a crashed cycle, so `_run_m4` records an all-zero roll-up. Two suites stub `run_b2` to return `None`."
  - "`tests/test_m4_gold.py` dropped its local `FakeMetrics` and imports the shared one, which leaves the module's other doubles (`FakeTable`, `FakeCatalog`) untouched while removing the duplication. This is the choice the plan asked to be recorded."
  - "`test_inclusive_durations_stay_on_the_cycle_record_only` scripts the clock rather than asserting `> 0`: a sub-millisecond fake run rounds the inclusive durations to zero and would have made the assertion vacuous."

patterns-established:
  - "A test double that asserts uniqueness surfaces ambiguity the previous idiom concealed; when a scenario legitimately breaks uniqueness, change the selector, not the expected value."

requirements-completed: [MTL-01, REGR-1, REGR-2, REGR-3]

duration: unrecorded
completed: 2026-08-18
---

# Phase 4 Plan 03: Cycle Identity in the Medallion Summary

**Every medallion record now names its cycle and its phase, the phase durations are disjoint, the cycle row is written last, and the cycle row carries the physical cost Prometheus used to see as zero.**

## What was built

**Task 1 — `068188d`.** `run()` generates one `cycle_id` per invocation with
`uuid.uuid4().hex`, following `iceberg_writer.py`'s `load_id` precedent, and threads it
through `_run_m4`, `_run_legacy` and `run_b2`. A `b2` + shadow cycle emits four records —
`b2`, `shadow`, `gold`, `cycle` — sharing that id, with the `cycle` record written last so
`observability/postgres_exporter.py`'s `distinct on (source)` keeps resolving to cycle
state rather than to a phase.

`B2Outcome` is a frozen dataclass of seventeen fields returned by `run_b2`. `_run_m4`
copies its physical-cost values onto the `cycle` record, so
`lakehouse_files{kind="planned"}`, `lakehouse_bytes`, `lakehouse_processed{kind="keys"}`
and `lakehouse_work` stop being published as zeros. `_read_persisted_silver` now returns
`(rows, snapshot_id)` and `_write_gold` returns the Gold snapshot id, which is what lets
Bronze, Silver and Gold snapshot identities land on the rows where they mean something.

**Task 2 — `6d2b9f9`.** All 34 `records[-1]` call sites across `tests/test_b2_medallion.py`,
`tests/test_medallion.py` and `tests/features/test_shadow_cutover.py` now name the record
they mean, via `metrics.phase("b2")` or the cycle accessors. `records[-1]` is exactly the
idiom that becomes ambiguous once one run emits several records — it silently starts
naming the last phase of the final cycle — so leaving it would have let the suite pass by
accident.

## Deviation: `FakeMetrics.cycles()`

This is a real plan deviation, and it was **discovered by the new uniqueness contract
itself** rather than anticipated.

The plan expected `tests/features/test_shadow_cutover.py` to need no behavioural change,
on the grounds that the cycle record is written last so every `records[-1]` assertion
would still resolve to it. That holds for single-run scenarios. But the rollback scenario
(`test_rolling_the_metrics_source_back_returns_to_the_validating_state`) deliberately runs
the medallion **twice**, so `cycle()` correctly refused to pick between two `cycle`
records — surfacing an ambiguity `records[-1]` had been hiding all along.

The plan's instruction was to stop and record why rather than adjust an expected number.
No expected value changed: `FakeMetrics.cycles()` was added, returning every `cycle`
record in write order, and the four shadow-cutover steps now say `cycles()[-1]`. That is
still unambiguous in the way `records[-1]` was not, because it can only ever resolve to a
cycle record, never to a phase of one.

## Verification performed

| Check | Result |
|---|---|
| `pytest -q --cov=iceberg --cov-fail-under=90` | **327 passed**, 61 deselected |
| Coverage gate | pass, **93.97%** (was 93.72% at 04-02) |
| `pytest -q tests/features -m "bdd and not integration and not airflow"` | **41 passed** |
| `pytest -q tests/test_m5_fitness_functions.py -m architecture` (REGR-4) | 12 passed |
| `pytest -q tests/test_m4_gold.py` | 21 passed (8 new MTL-01 tests) |
| `pytest -q tests/test_b2_medallion.py` incl. crash-before/after-commit recovery (REGR-1) | pass |
| `ruff check .` | All checks passed |
| `black --check .` | pass, 71 files unchanged |
| `git diff --exit-code iceberg/common/cutover.py` | clean |
| `git diff --exit-code tests/features/{shadow_cutover,silver_business_state}.feature` (REGR-3) | clean |
| `grep -c "records\[-1\]"` in the three target modules | 0 remaining |

### The `-m bdd` criterion was not executed as written

Task 2's acceptance criteria name `uv run --locked pytest -q tests/features -m bdd` as a
green gate. **That criterion is unmeetable in this plan's authorised environment**, and it
was not run as the gate. Running it yields 23 failures and 5 errors, all in modules that
carry a second marker alongside `bdd`:

| Module | Markers | Needs |
|---|---|---|
| `test_iceberg_writer.py` | `bdd, integration` | MinIO / REST catalog |
| `test_gold_cutover.py` | `bdd, integration` | MinIO / REST catalog |
| `test_writer_crash_recovery.py` | `bdd, integration` | MinIO / REST catalog |
| `test_airflow_workflow_behavior.py` | `bdd, airflow` | Airflow |

`AGENTS.md` treats those services as stateful and this plan is not authorised to start
them, so the substitute actually executed was
`pytest -q tests/features -m "bdd and not integration and not airflow"` → **41 passed**.
`tests/features/test_shadow_cutover.py` is the only `bdd`-only module Task 2 touches and
it is green. The plan's criterion is a defect: it implicitly assumes a live stack that its
own scope forbids. Plan 04-04 or 04-07 should restate it.

## Not verified

**No live stack was started.** No Docker service, MinIO bucket, Kafka topic, Spark
checkpoint, Iceberg table or PostgreSQL database was created, contacted or mutated.
Specifically **not** exercised:

- The four `integration`/`airflow` BDD modules above, including the writer crash-recovery
  and Gold-cutover features. Their behaviour under this change is unproven here; they run
  in `ci-integration.yml`, `ci-nightly.yml` and `ci-m5-gates.yml`, none of which were run.
- Real `marts.lakehouse_metrics` inserts. That four records per cycle land in PostgreSQL
  with the right columns is proven only against `FakeMetrics`, not a real cursor.
- Real Iceberg snapshot ids. `_snapshot_id`, `_read_persisted_silver` and `_write_gold`
  are exercised through `FakeTable`, whose fidelity to PyIceberg's snapshot semantics is
  asserted by construction.
- Prometheus scrape behaviour. That the cycle record's physical cost reaches
  `lakehouse_files{kind="planned"}` without being reset is a unit-level claim about the
  collector registry.
- Wall-clock duration behaviour. Every duration assertion runs on a scripted
  `time.monotonic`, deliberately, per threat T-04-09.

Row-growth impact (T-04-11) is accepted, not measured: this plan roughly doubles-to-
quadruples `marts.lakehouse_metrics` insert volume at a 60 s interval, and retention
remains out of scope.

## Commits

- `068188d` — feat(04-03): add medallion cycle and phase telemetry
- `6d2b9f9` — test(04-03): pin cycle contract across existing suites

## Note on history

This plan's execution was interrupted twice by an external process that auto-committed
the working tree with the message `1` and switched the checkout to `feat/SQLMesh`
(`3cdb556`, `1bc58c1` in the reflog). No work was lost. Both placeholder commits were
replaced by the two commits above via `git reset --soft bb068f5` and a
`--force-with-lease` push to `fork` only; the Task 1 / Task 2 boundary the plan defines
is preserved in the rewritten history.

## Interface for downstream plans

04-04 can rely on a `cycle`-phase record being the last write of every run, which is what
its stdout cycle-complete marker must agree with. 04-05 has `gold_snapshot_id` on both the
`gold` and `cycle` records, plus `B2Outcome.silver_snapshot_id`, for its no-op rebuild
skip. 04-06 has a measured `shadow` phase duration — the number SHD-01 drives toward zero.
04-07 must document the deliberate Prometheus per-phase exclusion, the unattributed
preamble residual, and the corrected `-m bdd` criterion.
