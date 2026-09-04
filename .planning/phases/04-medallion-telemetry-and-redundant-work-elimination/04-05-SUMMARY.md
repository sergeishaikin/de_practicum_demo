---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 05
subsystem: medallion
tags: [medallion, gold, provenance, iceberg, snapshot-properties, adr, memoization]

requires:
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 01
    provides: the snapshot-aware local FakeTable and the kwargs-tolerant run_b2 stub in tests/test_m4_gold.py
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 02
    provides: the gold_skipped / gold_snapshot_id columns and Metrics.record keyword parameters
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 03
    provides: _read_persisted_silver returning (rows, snapshot_id), and the gold phase record
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 04
    provides: CYCLE_COMPLETE_MARKER, CycleOutcome and a harness liveness proof that no longer assumes every cycle overwrites Gold
provides:
  - GOLD_SOURCE_SILVER_SNAPSHOT_KEY = "source-silver-snapshot-id", stamped on every Gold commit built from persisted Silver
  - _gold_provenance(gold), a current-snapshot-only, defensively parsed provenance read
  - _write_gold(catalog, gold_df, *, source_silver_snapshot_id) returning (written, gold_snapshot_id)
  - gold_skipped / gold_snapshot_id on the gold and cycle metric records
  - gold=skipped reachable in the cycle-complete stdout marker
  - ADR-0001 D-4 amended in the open, with its decision and all six reasons intact
affects: [04-06 shadow certificate, 04-07 documentation contract, 04-08 measurement]

tech-stack:
  added: []
  patterns:
    - "Memoize a full rebuild by stamping the identity of its input on the output commit; the catalog carries the provenance, so no sidecar can disagree with the table"
    - "Read provenance from current_snapshot() only — an external rewriter (Trino maintenance) then invalidates it automatically instead of a superseded snapshot vouching for replaced files"
    - "Every way of not knowing the answer rebuilds: absent, unparsable, stale and None all fail safe"
    - "Put the mode decision in the argument, not in the function: a nullable basis means one code path and no GOLD_SOURCE branching inside the writer"

key-files:
  created: []
  modified:
    - iceberg/medallion/iceberg_medallion.py
    - tests/test_m4_gold.py
    - docs/adr/0001-incremental-silver-and-gold.md
    - tests/features/shadow_cutover.feature
    - tests/features/test_shadow_cutover.py

key-decisions:
  - "The skip is scoped to GOLD_SOURCE=persisted_silver only. Under GOLD_SOURCE=legacy the Gold input is the in-memory legacy rebuild derived from Bronze, which a persisted-Silver stamp would not describe; that path passes None, always writes and never stamps. A Bronze-provenance skip for the legacy source is a separate decision and was not invented here."
  - "The decision lives inside _write_gold keyed on a nullable `source_silver_snapshot_id` rather than on a GOLD_SOURCE branch, so there is exactly one Gold write path and callers with no basis are safe by construction."
  - "`_gold_provenance` keeps `_snapshot_id`'s getattr/callable guard for consistency with the module's existing accessor. That leaves one defensive line uncovered (`iceberg_medallion.py:1138`); coverage stays above the gate at 94.12%."
  - "No new `status` literal for a skipped Gold. The exporter's SOURCE_UP set (observability/postgres_exporter.py) and the LakehouseApplicationFailure alert both key on `status`; a skip is expressed as `gold_skipped` plus `gold=skipped` in the marker instead."
  - "The `gold` phase record is still emitted when the write is skipped. Its duration_ms then measures the decision, which is precisely the number that demonstrates the saving against the 4.1-5.6 s baseline."
  - "The shadow_cutover rollback scenario was reworded from a write assertion to a state assertion because the operator locked that change, not because anything failed — with the persisted-Silver-only scoping the in-memory Silver double has no snapshots, so its id is None, Gold is never certified, and the old wording would have kept passing."
  - "gold_cutover.feature is untouched. 04-RESEARCH.md 4f names gold_cutover.feature:36 as a reword target; line 36 is the `Then the daily metrics are unchanged` step, which is already a state assertion, so the research reference is wrong."

patterns-established:
  - "Amend a ratified ADR in the open when code contradicts its literal wording: change the minimum number of words, keep every reason byte-identical, record it as a dated superseding section citing the measurement, and state the boundary the amendment does not cross."

requirements-completed: [GLD-01, MTL-01, REGR-1, REGR-2, REGR-3, REGR-4]

duration: unrecorded
completed: 2026-08-18
---

# Phase 4 Plan 05: Gold Provenance and the Elided Rebuild Summary

**Gold now records which persisted Silver snapshot produced it and declines to rebuild itself from a Silver snapshot it has already been built from — a memoization, not an incrementalisation, with ADR-0001 D-4 amended in the open to say so.**

## What the change actually is

`artifacts/b2-rollout/06-o1-window.json` records five outer cycles at demo volume. Gold
cost 4.1–5.6 s on **every** one of them, including the four that did no work at all. That
cost bought nothing: rebuilding a table from an input that has not moved produces the state
that is already there.

Gold stays a full, exactly verifiable rebuild whenever it runs. What is elided is a rebuild
whose result is provably identical to the Gold state already in the catalog. The evidence
for "provably identical" is the identity of the persisted Silver snapshot the current Gold
state was built from, stamped on the Gold commit as `source-silver-snapshot-id` — the same
snapshot-property idiom the medallion already uses for `silver-work-id` and the writer for
`load-id`.

## What was built

**Task 1 — `cf8405c`** (`iceberg/medallion/iceberg_medallion.py`).

`GOLD_SOURCE_SILVER_SNAPSHOT_KEY = "source-silver-snapshot-id"` sits next to
`SILVER_WORK_ID_KEY`.

`_gold_provenance(gold) -> int | None` reads `gold.current_snapshot()` and nothing else,
returning `None` for an absent current snapshot, an absent property, or a value that does
not parse as an integer. The docstring states why history is not walked, because that is
the security-relevant property of this change: `dags/lakehouse_maintenance.py` lists
`("gold", "orders_daily_metrics")` in `MAINTENANCE_TABLES`, and Trino `optimize` /
`expire_snapshots` rewrite Gold's files while knowing nothing about the property. Reading
only the current snapshot turns such a rewrite into automatic invalidation — provenance
reads as absent and the medallion rebuilds Gold once. Walking history would be fail-open: a
superseded or expired snapshot could vouch for files something else has since replaced.

`_write_gold(catalog, gold_df, *, source_silver_snapshot_id) -> tuple[bool, int | None]`
ensures and loads the table as before, then skips when the basis is not `None` and equals
`_gold_provenance(gold)`, and otherwise overwrites — passing `snapshot_properties` only when
there is a basis to stamp. Both traps the research names are respected explicitly: nothing
counts Gold snapshots (a full overwrite emits one snapshot the first time and two
thereafter, since the DELETE half is elided when nothing matches), and no empty
"stamp-only" overwrite is used to refresh provenance (the APPEND half is not elided for an
empty frame, so it would write a snapshot anyway and defeat the skip).

`_run_legacy` passes `None`. `_run_m4` passes `silver_snapshot_id` when
`GOLD_SOURCE == "persisted_silver"` and `None` otherwise. `gold_skipped=not gold_written`
rides the `gold` and `cycle` records; `CycleOutcome.gold` becomes `"rebuilt" if gold_written
else "skipped"` on both paths, so the marker reports what `_write_gold` did rather than what
the caller assumed. The `CycleOutcome` docstring, which 04-04 wrote as "only `rebuilt` is
reachable until GLD-01 lands the skip", now says both are reachable and what `skipped`
means.

**Task 2 — `432bb57`** (`tests/test_m4_gold.py`). Eight new tests, purely additive — the
diff is 168 insertions and zero deletions.

| Test | Row |
|---|---|
| `test_unchanged_persisted_silver_skips_the_gold_rebuild` | GLD-01a |
| `test_a_moved_silver_snapshot_rebuilds_gold` | GLD-01b |
| `test_a_gold_write_stamps_the_silver_snapshot_it_was_built_from` | GLD-01c |
| `test_gold_without_provenance_is_rebuilt` | GLD-01d |
| `test_provenance_is_read_from_the_current_snapshot_only` | GLD-01e |
| `test_a_silver_table_with_no_snapshots_is_never_certified` | T-04-18 |
| `test_unparsable_provenance_is_treated_as_absent` | T-04-19 |
| `test_legacy_gold_source_writes_every_cycle_and_stamps_nothing` | scope boundary |

GLD-01a also asserts `gold=skipped` in captured stdout and `gold_skipped is True` on both
the `gold` and `cycle` records, which is T-04-17: a skip must never be indistinguishable
from a write in the evidence. GLD-01e is the one that would fail if provenance were read by
walking history, and the snapshotless-Silver test is the one that would fail if `None ==
None` were allowed to certify. No test asserts a Gold snapshot count.

**The four pre-existing Gold contracts were run before any change and after, and none of
their expected values moved** — 4 passed both times. That was the plan's tripwire for
"scoping implemented more broadly than authorised", and it did not trip. They keep writing
Gold because `setup_gold_run` leaves the Silver double snapshotless, so `_snapshot_id`
returns `None`.

**Task 3 — `07c1d31`** (ADR + the ratified scenario).

ADR-0001 D-4's blockquote now reads *"rebuilt in full from persisted Silver on every cycle
in which persisted Silver changed."* The decision and all six reasons in the table are
byte-identical — the only other line touched in the body is the status header, which now
names the amendment. A new closing section, *Decision amendment — post Phase 4 (GLD-01)*,
follows the format of the existing post-SPIKE-2 amendment: it states that D-4's invariant
(Gold state is always the exact full rebuild of the current persisted Silver) is preserved,
that what changes is the elision of a rebuild producing a byte-identical result, cites
`artifacts/b2-rollout/06-o1-window.json`, and states the boundary — a partial or delta Gold
is outside the amendment and needs a fresh decision.

`shadow_cutover.feature:66` changed from *"Then the daily metrics are published again"* to
*"Then the daily metrics still reflect the current business state"*, and the matching step
now asserts the Gold content equals the metrics derived from the current business state
instead of `overwrite_calls == before + 1`. The now-unused
`context["gold_writes_before_rollback"]` assignment was removed with it. The two
neighbouring assertions in that scenario are untouched.

**This reword repaired no failure, and should not be read as one.** With the
persisted-Silver-only scoping, the in-memory Silver double in that feature has no snapshots,
so its snapshot id is `None`, so Gold is never certified and the old assertion would have
kept passing. It is a contract-clarity change the operator locked.

`tests/features/gold_cutover.feature` is byte-identical
(`git diff --exit-code` clean). `04-RESEARCH.md` §4f names `gold_cutover.feature:36` as a
reword target; line 36 is `Then the daily metrics are unchanged`, which is already a state
assertion — **the research reference is wrong** and the file was correctly left alone.

## Deviations from plan

**None that changed behaviour.** No premise the plan states diverged from the code's actual
behaviour, and no test, expected value or assertion was adjusted to make anything pass.

Two presentational choices worth recording:

1. The plan's Task 1 acceptance criterion asks that
   `grep -n "metadata.snapshots" iceberg/medallion/iceberg_medallion.py` show no new
   occurrence. The first draft of the `_gold_provenance` docstring named
   `metadata.snapshots` in prose while explaining why it is *not* used, which would have
   satisfied the intent but not the literal grep. The sentence was reworded to "the table's
   whole snapshot history". The only remaining hit is the pre-existing line 321 in
   `silver_committed_work_ids`.
2. The amendment section was initially appended without a blank line before its `---`
   separator, which Markdown would have parsed as a setext heading underline for the
   preceding paragraph. Fixed before commit.

**Nothing was done outside plan 04-05.** 04-06 and later plans were not started or prepared
for. The B2 algorithm, shadow comparison semantics, FF-14 rules and `RUNTIME_ROLLOUT_MATRIX`
were not touched; `iceberg/common/cutover.py` is byte-identical.

No documentation outside the ADR needed updating. `README.md:183` and
`docs/ARCHITECTURE.md:51` describe the medallion rebuilding Silver and Gold from Bronze
every 60 seconds — that is the legacy path (`SILVER_MODE` and `GOLD_SOURCE` both default to
`legacy`), which this change leaves exactly as it was. Nothing in `docs/` or `README.md`
mentions the cycle marker or `gold_skipped`.

## Verification performed

Every command below was executed in this session and these are its real figures.

| Check | Result |
|---|---|
| `uv run --locked pytest -q tests/test_m4_gold.py tests/test_m5_fitness_functions.py` (task 1 verify) | **34 passed** |
| `uv run --locked pytest -q tests/test_m5_fitness_functions.py -m architecture` (REGR-4) | **12 passed** |
| `git diff --exit-code iceberg/common/cutover.py` | clean |
| `grep -n "metadata.snapshots" iceberg/medallion/iceberg_medallion.py` | one hit, line 321, pre-existing |
| `uv run --locked pytest -q tests/test_m4_gold.py tests/test_b2_medallion.py` (task 2 verify) | **41 passed** |
| the four pre-existing Gold contracts, selected alone, **before** task 1 | **4 passed** |
| the same four, **after** tasks 1–3 | **4 passed**, expected values unedited |
| `git diff --stat tests/test_m4_gold.py` | 168 insertions, 0 deletions; 8 new `def test_` |
| `uv run --locked pytest -q tests/features/test_shadow_cutover.py -m bdd` (task 3 criterion) | **10 passed** |
| `uv run --locked pytest -q tests/features` (task 3 verify, default marker filter) | **41 passed, 23 deselected** |
| `grep -n "…on every cycle in which persisted Silver changed" docs/adr/0001-…md` | exactly one line (468) |
| `grep -c "…on every cycle\." docs/adr/0001-…md` | **0** |
| `grep -n "published again" tests/features/shadow_cutover.feature` | no matches |
| `grep -n "gold_writes_before_rollback" tests/features/test_shadow_cutover.py` | no matches |
| `git diff --exit-code tests/features/gold_cutover.feature` | clean (byte-identical) |
| `uv run --locked ruff check .` | All checks passed! |
| `uv run --locked black --check .` | 71 files would be left unchanged |
| `uv run --locked pytest` | **357 passed, 62 deselected** (baseline before this plan: 349) |
| `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | pass, **94.12%** total (was 94.10% after 04-04); `iceberg_medallion.py` **91%** |

Coverage note: the one new uncovered line is `iceberg_medallion.py:1138`, the
`return None` for a non-callable `current_snapshot` attribute in `_gold_provenance`. It is
the defensive guard `_snapshot_id` already uses, kept for consistency with the module's
existing accessor. `:1275` (`raise ValueError(f"Unsupported GOLD_SOURCE: …")`) was uncovered
before this plan too.

## Not verified — the live layer was **not executed here**

**No Docker service was started. No container, volume, checkpoint, Kafka record or Iceberg
table was created, contacted or mutated.** This execution was explicitly not authorised to
touch the stack. Specifically **not** run:

- `uv run --locked pytest -q tests/features -m "bdd and integration"` — including
  `gold_cutover.feature`, the live cutover/rollback walk.
- `uv run --locked pytest -q -m integration tests/integration/test_m3_b2_recovery.py tests/integration/test_m4_gold_cutover.py`.
- `ci-m5-gates.yml`, `ci-integration.yml`, `ci-nightly.yml`.

`ci-m5-gates.yml` is the gate that runs them on the PR, and this change touches
`iceberg/**` and `tests/test_*.py`, so it will trigger.

One observation worth stating precisely, since the plan asks for it rather than an
assumption. The plan's task-3 verify command is `pytest -q tests/features -m bdd`. That
command **overrides** `pytest.ini`'s `addopts = -m "not integration and not e2e and not
airflow"`, so it also selects the live-stack and Airflow scenarios: it reports 23 failed /
5 errors / 41 passed, every failure a `ConnectionRefusedError` against the absent local
catalog or an absent Airflow. Those files (`test_iceberg_writer.py`,
`test_writer_crash_recovery.py`, `test_airflow_workflow_behavior.py`,
`test_gold_cutover.py`) were not modified by this plan. The substitutes actually executed
were `pytest -q tests/features` (default filter, 41 passed) and
`pytest -q tests/features -m "bdd and not integration and not airflow and not e2e"`
(41 passed, 23 deselected).

What that leaves unproven, stated plainly: **that a real PyIceberg `overwrite` writes
`source-silver-snapshot-id` into the Gold snapshot summary and that
`table.current_snapshot().summary.additional_properties` reads it back across a real catalog
round trip** (GLD-01f, which 04-VALIDATION.md already assigns to the integration layer). The
skip decision, the fail-safe branches, the metric wiring and the marker value are all proved
in-process against doubles that mirror the PyIceberg slice in use; the catalog round trip is
not. Also unproven here: that `tests/integration/test_m4_gold_cutover.py` survives the skip.
It was read rather than run — it waits on Gold **row counts**
(`wait_for_gold_rows`), never on snapshot counts, and its rollback stage uses a fixed
`time.sleep(3)`, so it has no dependence on a Gold write happening per cycle.
`gold_snapshot_count` remains exported by `tests/support/medallion_harness.py` and is
called by no test.

## Commits

- `cf8405c` — feat(04-05): skip the Gold rebuild when persisted Silver has not moved
- `432bb57` — test(04-05): pin the Gold skip and every refusal to skip
- `07c1d31` — docs(04-05): amend ADR-0001 D-4 rather than silently violate it

## Interface for downstream plans

04-06 (the shadow certificate) may now assume `gold=skipped` is a reachable marker value and
that `gold_skipped` is a populated column on the `gold` and `cycle` rows. It must not reuse
`source-silver-snapshot-id` for a shadow certificate — that key names the Gold→Silver
relationship only — and it must not change `_write_gold`'s return contract.

04-07 (documentation) should document `source-silver-snapshot-id` as an operator-visible
property: it is how an operator reads, from the Gold table alone, which Silver snapshot the
published metrics describe. It should also document that a Trino maintenance run on Gold
costs exactly one extra rebuild on the next cycle, by design.

04-08 (measurement) can now compare the `gold` phase `duration_ms` on skipped versus
rebuilt cycles; the phase record is deliberately still emitted on a skip so that number
exists.

## Self-Check: PASSED

All five modified files and this SUMMARY exist on disk; all three task commits
(`cf8405c`, `432bb57`, `07c1d31`) are present in `git log`.
