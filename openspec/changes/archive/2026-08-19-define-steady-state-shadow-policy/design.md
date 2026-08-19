## Context

See proposal.md — Why. Two constraints shape everything below.

The first is that this change may not touch `iceberg/`. The policy question is
about a constant that already exists and already has the right value; the work
is to write down why it has that value and to make its shape assertable. Any
edit under `iceberg/` would turn analysis into implementation, which is the
failure mode `T-04-33` in the source plan names.

The second is that the cost evidence behind the policy is thin, and the ADR has
to say so at the point of use rather than in a footnote.
`artifacts/b2-rollout/06-o1-window.json` holds ten medallion metric rows from a
single six-minute window on 2026-08-10 at demo volume: five carry
`shadow_comparisons=1` with `silver_duration_ms` between 21406 and 45448 and
`gold_duration_ms` between 4130 and 5572, and exactly one row across the whole
window has non-zero `files_processed` and `snapshot_delta`. That establishes an
order of magnitude for one configuration on one dataset and **no scaling
relationship whatsoever**.

## Goals / Non-Goals

**Goals:**

- A ratified answer to the steady-state shadow question, with conditions a
  future proposal can be measured against rather than argued with.
- An assertion that fails when `RUNTIME_ROLLOUT_MATRIX` gains or loses a key.

**Non-Goals:**

- Implementing a steady-state evaluator. The ADR says whether the conditions
  *could* be expressed the way `evaluate_cutover_gate` expresses the cutover
  gate; it does not build one.
- Changing `docs/adr/0001-incremental-silver-and-gold.md`. 04-05 amended it; a
  second editor in the same phase makes the amendment history harder to read.
- Any measurement of the fast path's effect beyond what 04-06 already landed.

## Decisions

**An ADR rather than a remediation note.** The deliverable is a ratified policy
carrying conditions that a future change must satisfy, which is what an ADR is
for. `docs/remediation/` holds records of work done; this is a rule for work not
yet proposed. ADR-0001 already governs the neighbouring decisions, so the new
record sits beside it and cross-references rather than amends.

**Assert the key set and the rollout names together, not the keys alone.**
Equality on `set(RUNTIME_ROLLOUT_MATRIX)` catches an added or removed state but
not a silently re-pointed one — `("b2","legacy","1")` mapping to `cutover`
instead of `shadow` would pass a key-only assertion while inverting what the
matrix means. Asserting the full mapping costs nothing extra and closes that.
Alternative considered: assert only the keys, on the grounds that the names are
labels. Rejected — `validate_runtime_config` returns the name to its caller, so
the name is part of the contract, not decoration.

**Add a test; do not touch the two that exist.** `test_runtime_rollout_matrix_
accepts_safe_states` and `test_runtime_rollout_rejects_persisted_silver_without_
shadow` stay exactly as they are. They express a different thing — that specific
configurations are accepted and one specific configuration is refused — and
folding them into an exact-set assertion would lose the named rejection that
POL-01 cares most about. Note that the source plan describes the accepting test
as covering four configurations; it covers three, which is precisely why the
exact assertion is needed.

**Prove the assertion by making it fail.** A fitness test that has never been
observed to fail is a claim, not a check. The negative proof is: add a fifth key
to `RUNTIME_ROLLOUT_MATRIX`, run the new test, observe red, revert, and show
`git diff --exit-code iceberg/common/cutover.py` clean. The repository
established this convention in plan 03-01, and `verification-contract` now
requires it for exact-set assertions.

## Risks / Trade-offs

- **The negative proof requires temporarily editing a file the scope fence
  forbids changing.** → The fence is about the *end state* and is checked as
  `git diff --exit-code iceberg/`. The temporary edit is made, observed, and
  reverted within a single task, and the clean diff is the evidence that it was.
  Nothing is committed with the fifth key present.

- **An ADR can ratify a policy that later evidence contradicts.** → That is what
  the conditions section is for: it names what would have to be observed, over
  what window and at what volume, for a different answer to become proposable.
  The ADR is falsifiable by construction rather than permanent by assertion.

- **The cost argument leans on a fast path proved only by tests and a single
  demo-volume window.** → Every cost claim in the ADR carries that limit inline,
  in the style Phase 3 established, so a reader cannot mistake an order of
  magnitude for a measured scaling law.

## Migration Plan

None. No runtime behaviour changes, no configuration changes, nothing to deploy
or roll back. The rollout matrix is byte-identical before and after.
