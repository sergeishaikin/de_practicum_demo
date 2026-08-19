## Why

Since M5 the repository has behaved as though `SHADOW_COMPARE` must stay
permanently enabled after a successful cutover, but that answer was never
written down with its conditions. An unstated policy cannot be argued with: no
one can tell what evidence would change it, and a future proposal to relax it
has nothing to be measured against.

Two things now make the question answerable rather than merely arguable. The
receipt-gated fast path landed in 04-06 removed the standing cost objection for
cycles over unmoved state, so the argument's shape has changed. And the rollout
matrix that enforces the policy is only partially pinned: today a test rejects
the one forbidden combination `(b2, persisted_silver, 0)`, so a *different* key
could be added to `RUNTIME_ROLLOUT_MATRIX` without any test noticing — which is
exactly the risk POL-01 names.

This is the OpenSpec change that carries the obligation migrated from
`.planning/phases/04-medallion-telemetry-and-redundant-work-elimination/04-08-PLAN.md`.

## What Changes

- A ratified ADR, `docs/adr/0002-steady-state-shadow-policy.md`, answering
  whether shadow validation must remain on forever after cutover, evaluating all
  four locked candidate policies, and stating the evidence and safety conditions
  any future move would have to satisfy.
- One added architecture fitness test asserting that
  `RUNTIME_ROLLOUT_MATRIX` holds *exactly* its four accepted keys with exactly
  their four rollout names, so a fifth key fails a test rather than passing
  unnoticed.

Not breaking. No runtime behaviour changes.

**Scope fence, checkable rather than descriptive:**

- `git diff --exit-code iceberg/` SHALL be clean at the end of this change.
  `iceberg/common/cutover.py` is not edited, and `(b2, persisted_silver, 0)` is
  not added to the matrix under any circumstances.
- `git diff --exit-code docs/adr/0001-incremental-silver-and-gold.md` SHALL be
  clean — 04-05 already amended it and a second editor would obscure the
  amendment history.
- The two pre-existing rollout tests are not weakened, merged or deleted.
- No live stack is started; this change needs none.
- Work stops at the end of this change. `04-09` is not begun.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `verification-contract`: adds a requirement that a closed set of accepted
  architectural states is asserted by equality rather than by membership. The
  existing rules say a check must be executed and must be demonstrated to fail
  without the fix; neither of them catches a check that runs, passes, and tests
  less than it appears to. That is the defect class this change repairs in the
  rollout matrix, and it is a rule about what counts as verified, not an
  implementation detail.

## Impact

- `docs/adr/0002-steady-state-shadow-policy.md` — new.
- `tests/test_m5_fitness_functions.py` — one added `architecture`-marked test.
- `openspec/specs/verification-contract/spec.md` — one added requirement.
- `iceberg/` — deliberately untouched; this change is analysis plus a test.
- Requirements addressed: POL-01, REGR-4.
