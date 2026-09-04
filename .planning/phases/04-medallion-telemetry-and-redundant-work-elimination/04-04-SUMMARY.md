---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 04
subsystem: observability
tags: [medallion, telemetry, testing, harness, liveness, iceberg]

requires:
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 03
    provides: the cycle_id threaded through run() / _run_m4 / _run_legacy and the cycle-phase record whose duration_ms the marker republishes
provides:
  - CYCLE_COMPLETE_MARKER and one flushed stdout line per completed cycle, emitted from a single site in run()
  - CycleOutcome, the frozen per-cycle decision record _run_m4 and _run_legacy return
  - parse_cycle_marker, a total parser that rejects anything not led by the marker token
  - CycleWatcher, draining both child pipes on daemon threads, with wait_for_cycle_complete(timeout, gold, shadow) and output()
  - run_deployment liveness proved by an announced cycle rather than a Gold snapshot
  - gold_snapshot_count retained for the inverted assertions 04-05 and 04-06 need
affects: [04-05 Gold skip, 04-06 shadow certificate, 04-07 documentation contract]

tech-stack:
  added: []
  patterns:
    - "A liveness signal that cannot be switched off: stdout, unconditional, flushed, one emit site"
    - "A total parser in a test harness — an unrecognised line is not a marker, never an exception"
    - "Absence of a signal is itself the signal: an aborted or early-returning cycle stays silent"

key-files:
  created: []
  modified:
    - iceberg/medallion/iceberg_medallion.py
    - tests/support/medallion_harness.py
    - tests/test_medallion.py

key-decisions:
  - "The marker vocabulary is fixed now and defined in the `CycleOutcome` docstring rather than as five module constants. `gold=skipped` and `shadow=skipped` are documented but unreachable until 04-05 and 04-06; introducing symbols nothing yet assigns would have been dead code in this wave, and the docstring is where a reader of the format contract looks."
  - "`wait_for_cycle_complete` is exposed as a `CycleWatcher` method only, not additionally as a module-level function. The plan made the module-level convenience conditional (\"if exposed\"), and a free function wrapping one watcher method is indirection without a caller. `__all__` therefore exports `parse_cycle_marker`, `CycleWatcher` and `gold_snapshot_count`."
  - "`CycleWatcher` fails fast when the child has exited, both drain threads are finished and the marker queue is empty — a dead deployment cannot still announce a cycle, so waiting out 90 s would only delay the diagnosis. This is why the fake process in the tests carries a `poll()`. The queue is checked last so a marker that arrived between the caller's timeout and the check still counts as a completed cycle."
  - "`run_deployment` closes the watcher *after* `process.terminate()`/`wait()`, inside a nested `finally`, so the drain threads join at real EOF rather than being asked to stop while the child is still writing."
  - "`parse_cycle_marker` requires the marker to be the line's first field and requires the field set to be exactly the four names (T-04-12). A diagnostic that merely quotes a marker cannot make a deployment look alive."

patterns-established:
  - "When a test harness's liveness proof depends on a production invariant, replace the proof one wave before the invariant is deleted, so CI exercises the replacement while the two are still equivalent."

requirements-completed: [MTL-01, REGR-1, REGR-2]

duration: unrecorded
completed: 2026-08-18
---

# Phase 4 Plan 04: Cycle-Complete Liveness Marker Summary

**A completed medallion cycle now announces itself once on stdout with its cycle id and its gold/shadow decisions, and the integration harness reads that announcement instead of assuming every cycle overwrites Gold.**

## Why this landed before GLD-01

`tests/support/medallion_harness.py` encoded "every cycle ends in a Gold overwrite" as the
definition of a deployment having done work, and `run_deployment` called
`wait_for_new_gold_snapshot` unconditionally on every stage. `gold_cutover.feature` walks
three deployments over a lake whose Silver deliberately does not change — that is the point
of the scenario — so the moment the 04-05 Gold skip lands, deployments 2 and 3 would burn
90 s each and fail. `ci-m5-gates.yml` triggers on `iceberg/**` and `tests/support/**`, so
that is a PR blocker.

Landing the replacement one wave earlier means the new signal is exercised by CI while it
is still exactly equivalent to the old one. A parser bug shows up now, as a normal test
failure, instead of later, disguised as the behaviour change.

## What was built

**Task 1 — `2918f4a`.** `CYCLE_COMPLETE_MARKER = "cycle-complete"` and a frozen
`CycleOutcome(cycle_id, gold, shadow, duration_ms)`. `_run_m4` and `_run_legacy` now return
a `CycleOutcome` on completion and `None` otherwise; `run()` renders it at the single emit
site:

```
cycle-complete cycle_id=<hex> gold=<rebuilt|skipped> shadow=<compared|skipped|disabled> duration_ms=<int>
```

`duration_ms` is the *same variable* the `cycle` metrics record carries — hoisted into
`duration_ms` / `cycle_duration_ms` rather than recomputed — so a log line and a metrics row
about the same cycle can never disagree, and no extra `time.monotonic()` call was
introduced (which would have broken the `scripted_monotonic` assertions from 04-03).

Silence is load-bearing. `_legacy_silver_cycle` returning `None` (no Bronze, or a fatal
quality violation) and the shadow-mismatch `raise` both leave `run()` without an outcome, so
no marker is printed. A comment at the raise site says so explicitly, because "no marker"
is how the harness learns a deployment did not complete.

`run()`'s branch structure was flattened (unsupported-mode check first, then one
`if/else` producing `cycle`) so there is exactly one exit through the print. The
`ValueError("Unsupported SILVER_MODE: …")` message and the routing are unchanged.

**Task 2 — `fa11804`.** `parse_cycle_marker` returns a mapping or `None`, never raises:
the token must be the first field, the field set must be exactly the four names, and
`duration_ms` must parse as an `int`. `CycleWatcher` drains **both** `stdout` and `stderr`
on daemon threads — `start_medallion` pipes both and the old `run_deployment` read neither,
a latent stall that predates this change (T-04-13). `wait_for_cycle_complete` returns the
first marker matching the optional `gold`/`shadow` filter and raises an `AssertionError`
quoting everything captured; `output()` exposes that capture.

`run_deployment` now creates the watcher immediately after `start_medallion`, waits on an
announced cycle, keeps `await_load_id` / `await_gold_rows` / `assert process.poll() is None`
untouched, and closes the watcher in the `finally` alongside `terminate()`.
`wait_for_new_gold_snapshot` is gone; `gold_snapshot_count` is kept, because 04-05 and 04-06
need it to assert the opposite property.

`tests/features/test_gold_cutover.py` is byte-identical, as required. Its
`unvalidated_cutover` step calls `h.start_medallion` and `process.communicate` directly —
it never goes through `run_deployment`, so no watcher exists for that process and the two
ways of reading a pipe never contend for the same child. Verified by reading the step, and
by both files' SHA-256 being unchanged.

**Task 3 — `2064ddb`.** Ten parser assertions (well-formed, int coercion, empty line, blank
line, an ordinary log line, a line that only quotes the marker, a valueless field, a missing
field, a non-integer duration, an unknown extra field) and four watcher tests, all in the
default fast suite with no marker and no stack. The watcher is driven by a `FakeProcess`
whose pipes are lists of lines; every wait is on the watcher's own API, and no `time.sleep`
was added.

Importing `tests.support.medallion_harness` was checked and is inert: `writer_harness`
constructs `RestCatalog` and `S3FileSystem` inside `catalog()` and `fs()`, never at module
scope. The whole file is import-time env reads plus definitions. The operational proof is
that the new tests run green in the default suite with no stack running.

## Deviations from plan

**None.** No premise in the plan diverged from the code's actual behaviour. Two choices the
plan left open were decided and are recorded in `key-decisions` above (marker vocabulary as
docstring rather than constants; `wait_for_cycle_complete` as a method only). One small
addition beyond the literal action text — `CycleWatcher` failing fast once the child has
exited and both pipes are at EOF — is what makes the plan's own `poll()`-bearing fake
process meaningful, and is covered by a test.

## Verification performed

Every command below was executed in this session and these are its real figures.

| Check | Result |
|---|---|
| `uv run --locked pytest -q tests/test_medallion.py tests/test_m4_gold.py` (task 1) | **49 passed** |
| `uv run --locked pytest -q --collect-only tests/features/test_gold_cutover.py -m integration` (task 2) | **2 tests collected** |
| `uv run --locked pytest -q tests/test_medallion.py` (task 3) | **41 passed** |
| `uv run --locked ruff check .` | All checks passed! |
| `uv run --locked black --check .` | 71 files would be left unchanged |
| `uv run --locked pytest` | **349 passed, 62 deselected** (baseline before this plan: 328) |
| `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | pass, **94.10%** total (was 93.66% in AGENTS.md); `iceberg_medallion.py` 91% |
| `uv run --locked pytest -q tests/features -m "bdd and not integration and not airflow"` | 41 passed, 23 deselected |
| `uv run --locked pytest -q tests/test_b2_medallion.py` (REGR-1, REGR-2) | 11 passed |
| `uv run --locked pytest -q tests/test_m5_fitness_functions.py -m architecture` (REGR-4) | 12 passed |
| `grep -rnI "wait_for_new_gold_snapshot" tests/` | no matches |
| `grep -rnI "Every cycle ends in a Gold overwrite" tests/` | no matches |
| `grep -n "time.sleep" tests/test_medallion.py` | no occurrences |
| SHA-256 of `tests/features/test_gold_cutover.py` and `gold_cutover.feature` | unchanged from pre-task state |

A note on the greps: run without `-I`, both patterns also match a stale
`tests/support/__pycache__/medallion_harness.cpython-313.pyc` left from before the edit.
That is untracked bytecode, not source. The figures above are text-only matches.

Coverage note: `iceberg_medallion.py:1356`
(`raise ValueError(f"Unsupported SILVER_MODE: …")`) is uncovered. It was uncovered before
this plan too — the same statement at line 1299 of the base revision — so this is not a
regression introduced here. No test exercises an unsupported `SILVER_MODE`.

## Not verified — the live layer was **not executed here**

**No Docker service was started. No container, volume, checkpoint, Kafka topic, MinIO
bucket or Iceberg table was created, contacted or mutated.** This execution was explicitly
not authorised to touch the stack, and the plan is designed so the live layer is proved by
CI on the PR instead. Specifically **not** run:

- `uv run --locked pytest -q tests/features -m "bdd and integration"` — including
  `gold_cutover.feature`, the feature this change exists to keep green.
- `uv run --locked pytest -q -m integration tests/integration/test_m3_b2_recovery.py tests/integration/test_m4_gold_cutover.py`.
- `ci-m5-gates.yml`, `ci-integration.yml`, `ci-nightly.yml`.

The substitutes actually executed in their place are the fast-suite rows above:
`--collect-only -m integration` on the cutover module (import and collection only), the
offline BDD subset, and the stackless parser/watcher tests.

What that leaves unproven, stated plainly: **that a real medallion subprocess emits the
marker down a real pipe, and that `CycleWatcher` reads it from that pipe within the
timeout.** The parser, the watcher's queueing and filtering, the emit site and the silence
of the abort paths are all proved in-process; the subprocess/pipe wiring between them is
not. `ci-m5-gates.yml` runs it on the PR, which is the point of landing this a wave before
GLD-01.

Also unproven here: the marker's behaviour under a real Iceberg catalog's timing (the
`duration_ms` values in tests come from a fake clock-free run), and thread-shutdown
behaviour against a real terminated child (`close()` is exercised only against fakes whose
streams end immediately).

## Commits

- `2918f4a` — feat(04-04): announce every completed medallion cycle on stdout
- `fa11804` — refactor(04-04): prove deployment liveness from an announced cycle
- `2064ddb` — test(04-04): prove the marker parser and watcher without a stack

## Interface for downstream plans

04-05 (GLD-01) sets `gold="skipped"` on the `CycleOutcome` it returns when it decides Gold
is already current; the marker format needs no change, and
`watcher.wait_for_cycle_complete(gold="skipped")` is the assertion that the skip actually
happened rather than merely not happening to write. `gold_snapshot_count` is still there
for the inverse assertion. 04-06 does the same with `shadow="skipped"`. Neither may alter
the marker's field names, order or vocabulary — the parser pins all three, and
`tests/test_medallion.py::TestParseCycleMarker` will say so.

04-07 should document the marker as an operator-visible contract: it is the one line an
operator can grep to see that a deployment is alive and what each cycle decided.

## Self-Check: PASSED

All three modified files and this SUMMARY exist on disk; all three task commits
(`2918f4a`, `fa11804`, `2064ddb`) are present in `git log`.
