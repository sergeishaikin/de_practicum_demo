# Evidence — profile-arrow-python-boundary

## The measurement

`scripts/profile_arrow_boundary.py`, four delta sizes spanning six orders of
magnitude, medians over a recorded repeat count, no live service. Python 3.12.12,
pyarrow 21.0.0. All figures in milliseconds.

| rows | keys | rep | Arrow→Py delta | Arrow→Py current | collapse | resolve | Py→Arrow | Σ steps | production sequence |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 21 | 0.070 | 0.039 | 0.003 | 0.003 | 0.075 | 0.190 | **0.193** |
| 100 | 50 | 21 | 1.183 | 0.282 | 0.158 | 0.164 | 0.125 | 1.913 | 1.941 |
| 10 000 | 5 000 | 7 | 102.659 | 25.353 | 15.392 | 17.655 | 5.304 | 166.363 | 162.758 |
| 1 000 000 | 500 000 | 3 | 14 438.614 | 2 940.427 | 2 441.702 | 2 748.801 | 862.028 | 23 431.572 | 21 586.585 |

Row counts check out at every size: 100 rows over 50 keys collapse to 50 and
resolve to 50, with the delta carrying versions 1 and 2 per key against current
state at version 1.

## Disposition

**`NOT WORTH DOING (unmeasurable baseline)`**, by the rule fixed in `design.md`
before the numbers were read.

At the only delta size this pipeline has ever been observed to produce — one key,
one row, 4 422 bytes, from `06-o1-window.json` — the entire boundary costs
**0.193 ms** end to end. Negligible in absolute terms by any reading.

The `(unmeasurable baseline)` qualifier is not a hedge about the measurement,
which is sound. It records that `artifacts/phase-04/04-bench-summary.json` does
not exist, so there is no post-change cycle duration to express even a large
boundary cost as a share of.

**Flip point.** The boundary reaches one second of wall time at roughly
**46 325–61 440 rows**, interpolating the two large points (21.59 µs/row at 10⁶,
16.28 µs/row at 10⁴). Two points and linear interpolation, not a fitted model —
per-row cost is not constant across the sweep. One second is an absolute
reference, deliberately not a share of a cycle, because no measured cycle exists
to take a share of.

## Branch B adaptation — the change's central deviation

The plan's Branch B expects `04-bench-summary.json` to exist carrying
`disposition: "NOT MEASURED"` and a `reason` to quote. The actual state is a
third one the branch text does not anticipate:

```text
$ ls artifacts/phase-04/
ls: cannot access 'artifacts/phase-04/': No such file or directory
```

The directory did not exist. `04-09` was never authorised, so it never ran and
never wrote a receipt. The artifact records this as absence with its cause, and
attributes **no** `disposition` and **no** `reason` to a file that has never
contained either — both fields are explicitly `null` in the receipt. No stub was
created; `find` over the tree confirms no `04-bench-summary.json` exists
anywhere.

The plan's own `must_haves` sanction this form directly: *"or the absence of that
profile is recorded as the reason it could not be."* The invariant is met by
recording the absence, not by inventing the input.

No substitute denominator was derived. The pre-change window in
`06-o1-window.json` was produced by different code — before the Gold rebuild skip
and the receipt-gated fast path — so using it would express today's boundary as a
share of yesterday's cycle.

## A correction made during the work

`design.md` originally justified the extra `production_sequence` measurement on
the reasoning that summing the four named steps would **understate** what a cycle
pays, because the sequence collapses the delta twice. **That reasoning was
wrong**, and the measurement is what exposed it: `resolve_against_current`
measured on its own already includes its internal collapse, so the per-step sum
covers both collapses too. Sum and sequence agree within 8 % at every size, and
at 10⁶ the sum is the larger of the two.

Both `design.md` and the script comment were corrected to say what the data
shows. The sequence measurement was kept for a weaker but real reason: it is the
only figure corresponding to work a cycle executes end to end, and it
independently confirms the per-step sum is not an artefact of measuring in
isolation.

## Where the time actually goes

The dominant cost is **Arrow-to-Python conversion**, not the Python resolution
logic. At 10⁶ rows the two `to_pylist()` calls cost ≈ 17.4 s of the 21.6 s
sequence; `collapse_delta` and `resolve_against_current` together cost ≈ 5.2 s.

This matters for the locked instruction, which prefers an Arrow-native or
vectorised implementation. Were an optimisation ever justified, this measurement
says where it would have to be aimed: at the conversions. Vectorising the
resolution logic while leaving `to_pylist()` in place would address the smaller
share.

## Finding carried to a separate authorisation

**Double collapse.** `iceberg/medallion/iceberg_medallion.py:621` calls
`collapse_delta(incoming)`; line 630 calls
`resolve_against_current(current, incoming)`, which calls `collapse_delta` on the
same input again. The delta is collapsed twice per cycle.

- **Correctness:** neutral. `collapse_delta` is pure and deterministic, so the
  second call returns the first call's result.
- **Measured cost:** 11.3 % of the production sequence at 10⁶ rows, 1.3 % at one
  row.
- **Status:** reported, **not fixed**. A fix would change `iceberg/`, which this
  change is forbidden to touch. Per the authorisation, the work stops here and
  the finding is carried to a separate authorisation rather than widening 04-10.

## Gates

| Command | Result |
|---|---|
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked black --check .` | `72 files would be left unchanged` |
| `uv run --locked pytest` | `398 passed, 63 deselected` |
| coverage gate, `--cov-fail-under=90` | `Total coverage: 94.28%` |
| artifact shape assertions | `artifact shape PASS` |

The suite figures are unchanged from the previous commit, which is expected: this
change adds a one-off script and an artifact, and no test.

## Scope fence, verified

| Fence | Check | Result |
|---|---|---|
| `iceberg/` unmodified | `git diff --exit-code iceberg/` | clean |
| No production code changed | `code_changed: []`, `iceberg_modified: false` in the receipt | holds |
| No stub benchmark summary | `find . -name "04-bench-summary.json"` outside `.venv` | no match |
| No fabricated disposition or reason | both `null` in `branch_adaptation`, asserted | holds |
| `OPTIMISE` unreachable | disposition asserted `!= "OPTIMISE"` | holds |
| No new dependency | script imports stdlib, `pyarrow`, and `b2_spike` | holds |
| No live service | pure functions over synthetic rows; nothing connected | holds |
| `04-09` not started | no benchmark run, no canonical state touched | holds |
