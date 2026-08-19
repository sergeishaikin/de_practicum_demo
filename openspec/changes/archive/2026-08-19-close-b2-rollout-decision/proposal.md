## Why

DEC-01 has been open since the B2 controlled rollout finished. Plan 01-06
collected a valid O1 telemetry window and passed its gate on 2026-08-10, and
nothing has consumed that evidence since: the deferred items D-3a (physical
layout tuning) and O2 (tracing) sit in an undecided state, which is worse than
either answer because it is indistinguishable from "not looked at".

The evidence does not need judgement to resolve. The gate's own rules select
exactly one outcome from what was measured, and this change records that
selection as a deterministic result rather than as an expert opinion.

This is the OpenSpec change that carries the obligation migrated from
`.planning/phases/01-b2-controlled-rollout/01-07-PLAN.md`.

## What Changes

- `artifacts/b2-rollout/07-rollout-decision.json` — the machine-readable DEC-01
  receipt with exactly one outcome, `no_change`, evidence paths and hashes, gate
  statuses, runtime disposition, rollback status, and explicit reasons for
  rejecting each of the other two outcomes.
- `artifacts/b2-rollout/07-rollout-result.md` — the human-reviewable ledger of
  the same decision.
- `.planning/STATE.md` — ledger entry recording that the obligation was
  discharged here.
- `openspec/specs/engineering-governance/spec.md` — one added requirement, see
  Capabilities.

Not breaking. No runtime behaviour changes, no code changes.

**Scope fence, checkable rather than descriptive:**

- No implementation of D-3a or O2. `implementation_changes` in the receipt is
  the empty list and is asserted to be.
- No physical layout change, no progress-protocol change, no orchestration
  change, no multi-writer work, no architecture change.
- The historical evidence artifacts under `artifacts/b2-rollout/` are read and
  hashed, never modified: `git diff --exit-code` over every input artifact must
  be clean.
- No live stack is started. The evidence window is frozen and dated 2026-08-10;
  nothing here reproduces it.
- `04-09` is not touched. `04-10` is not begun.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `engineering-governance`: adds a requirement that a decision to defer records
  what would reopen it, and is not recorded as a refutation. `no_change` here
  means *do not open D-3a and O2 now*, on this evidence; it is not a finding
  that they are unnecessary. Without that rule written down, the natural way to
  read a closed decision is as a settled question, and the next reader inherits
  a conclusion the evidence never supported. This is a rule about what a
  planning record may claim, which is a governance behaviour rather than an
  implementation detail.

## Impact

- `artifacts/b2-rollout/` — two new files; every existing file read-only.
- `.planning/STATE.md` — migration ledger only.
- `openspec/specs/engineering-governance/spec.md` — one added requirement.
- No source file under `iceberg/`, `spark/`, `dags/` or `dbt/` is touched.
- Requirements addressed: DEC-01.
