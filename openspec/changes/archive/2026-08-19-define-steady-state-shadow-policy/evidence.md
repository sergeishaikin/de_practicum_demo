# Evidence — define-steady-state-shadow-policy

## Negative proof of the exact-set assertion

`verification-contract` now requires that an exact-set assertion be demonstrated
to fail, not assumed to. Three mutations were made to `RUNTIME_ROLLOUT_MATRIX`,
each reverted immediately after the observation.

### 1. The forbidden key

Added `("b2", "persisted_silver", "0"): "steady"`.

```text
FAILED tests/test_m5_fitness_functions.py::test_runtime_rollout_matrix_holds_exactly_the_four_accepted_states
FAILED tests/test_m5_fitness_functions.py::test_runtime_rollout_rejects_persisted_silver_without_shadow
2 failed, 11 passed

E   AssertionError: Left contains 1 more item:
E   {('b2', 'persisted_silver', '0'): 'steady'}
E   Failed: DID NOT RAISE <class 'ValueError'>
```

Both the new assertion and the pre-existing rejection test caught it. That is
the one addition the repository could already detect.

### 2. A key the pre-existing tests cannot see — the decisive case

Added `("legacy", "persisted_silver", "1"): "hybrid"`.

```text
FAILED tests/test_m5_fitness_functions.py::test_runtime_rollout_matrix_holds_exactly_the_four_accepted_states
1 failed, 12 passed

E   AssertionError: Left contains 1 more item:
E   {('legacy', 'persisted_silver', '1'): 'hybrid'}
```

**Only the new test failed.** Every pre-existing architecture test passed with a
fifth accepted rollout state present in the matrix. This is the coverage gap
POL-01 names, reproduced and then closed.

### 3. Removal

Removed `("b2", "legacy", "0"): "rollback"`.

```text
FAILED tests/test_m5_fitness_functions.py::test_runtime_rollout_matrix_holds_exactly_the_four_accepted_states
1 failed, 12 passed
```

Again only the new test failed, which incidentally confirms the discrepancy
recorded below: no pre-existing test covers the `rollback` state at all.

### Restoration

```text
$ git checkout -- iceberg/common/cutover.py
$ git diff --exit-code iceberg/common/cutover.py
cutover.py: byte-identical
```

`git status --porcelain` at the end of the task showed only
`tests/test_m5_fitness_functions.py`, the new ADR and this change directory.

## Gate figures

Every command was executed; none is reported from memory.

| Command | Result |
|---|---|
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked black --check .` | `71 files would be left unchanged` |
| `uv run --locked pytest` | `398 passed, 63 deselected in 2.90s` |
| `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | `Required test coverage of 90% reached. Total coverage: 94.28%` — `398 passed, 63 deselected` |
| `uv run --locked pytest -q tests/test_m5_fitness_functions.py -m architecture` | `13 passed` (12 before this change) |

The fast suite moved from 397 to 398 passing, which is the single test this
change adds. No test was deselected that was previously selected.

**Not executed:** nothing in this change needs a live stack, and none was
started. The live proof that matters here is the repository CI on the pushed
SHA, recorded below.

## Discrepancies found between the source plan and the code

Recorded rather than silently worked around, as `engineering-governance`
requires.

1. **`04-08-PLAN.md` describes `test_runtime_rollout_matrix_accepts_safe_states`
   as parametrising "the four accepted configurations". It parametrises three** —
   `legacy`, `shadow` and `cutover`. `("b2", "legacy", "0") → "rollback"` is
   covered by no test in `tests/test_m5_fitness_functions.py`. Proof 3 above
   demonstrates this directly: deleting that key left every pre-existing test
   green. The discrepancy strengthens the plan's own argument rather than
   contradicting it, so the work proceeded; the plan's description is what is
   wrong, not its instruction.

2. **The informal policy statement in `.planning/STATE.md` is imprecise.** It
   reads *"Persisted-Silver Gold cutover must keep shadow comparison enabled"*,
   which is easy to read as "`SHADOW_COMPARE=1` always". The matrix itself
   accepts `("b2", "legacy", "0")` — validation off while Gold is served from
   the legacy projection — so an unconditional reading would contradict the
   constant it is supposed to justify. ADR-0002 states the rule in its
   conditional form: whenever `GOLD_SOURCE=persisted_silver`, `SHADOW_COMPARE`
   SHALL be `1`.

3. **The plan's phrase "five cycles … one of which did real work" needs its
   row-level form to be checkable.** `06-o1-window.json` holds ten metric rows
   for those five outer cycles: five carry `shadow_comparisons=1`, and exactly
   one row in the window has non-zero `files_processed` and `snapshot_delta`.
   The ADR quotes the row-level figures and the five-cycle framing together, so
   neither reading can be mistaken for a measurement it is not. ADR-0001's
   post-Phase-4 amendment already uses the five-cycle framing, and this record
   stays consistent with it.

## Scope fence, verified

| Fence | Check | Result |
|---|---|---|
| `iceberg/` untouched | `git diff --exit-code iceberg/` | clean |
| ADR-0001 untouched | `git diff --exit-code docs/adr/0001-incremental-silver-and-gold.md` | clean |
| `(b2, persisted_silver, 0)` not added | proof 1 reverted; matrix byte-identical | holds |
| Pre-existing rollout tests unchanged | both present and passing, no edits | holds |
| No live stack started | none required, none started | holds |
| `04-09` not begun | no benchmark work, no canonical state touched | holds |
