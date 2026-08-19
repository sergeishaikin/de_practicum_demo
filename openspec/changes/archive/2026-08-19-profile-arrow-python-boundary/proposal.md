## Why

PRF-01 is the last open requirement of Phase 4 and the only one still stated as a
question: is the Arrow/Python boundary in the B2 Silver path worth optimising,
now that the redundant full-state work is gone? The locked instruction is to
optimise **only if still measurable**, which cannot be evaluated because the
boundary has never been measured — every claim about it so far has been
inference from reading code.

This change measures it and records the answer. A result of "not worth doing" is
a complete, successful outcome for PRF-01, not a failure to find something.

This is the OpenSpec change that carries the obligation migrated from
`.planning/phases/04-medallion-telemetry-and-redundant-work-elimination/04-10-PLAN.md`.

## What Changes

- `scripts/profile_arrow_boundary.py` — a one-off measurement of the four
  boundary steps, following `scripts/verify_m5_cutover.py`'s shape: arguments in,
  JSON out, no live service.
- `artifacts/phase-04/04-arrow-boundary-profile.json` — the measured profile, its
  `disposition`, the reasoning behind that disposition, and the delta size at
  which the conclusion would flip.
- `docs/adr/0002-steady-state-shadow-policy.md` — a short cross-reference note
  pointing at the profile artifact. Nothing about the shadow policy changes.

Not breaking. No production code changes.

**The plan's Branch B is adapted, and this is the change's central deviation.**
04-10 defines a branch for the case where BENCH-01 was *refused*, in which
`artifacts/phase-04/04-bench-summary.json` exists carrying
`disposition: "NOT MEASURED"` and a `reason` to quote. The actual state is a
third one the branch text does not anticipate: `artifacts/phase-04/` does not
exist at all, because `04-09` was never authorised and so never produced a
receipt. The plan's own `must_haves` already sanction this — *"or the absence of
that profile is recorded as the reason it could not be"* — so the invariant is
satisfied by recording the absence, not by inventing the artifact.

**Scope fence, checkable rather than descriptive:**

- `git diff --exit-code iceberg/` SHALL be clean. No production code changes, on
  any branch, for any reason.
- No stub, placeholder or fabricated `04-bench-summary.json` is created, and no
  `disposition` or `reason` is attributed to an artifact that does not exist.
- `OPTIMISE` is unreachable: without a measured post-change cycle there is no
  denominator, and an optimisation cannot be justified against one that was never
  measured.
- No new dependency, no new language or toolchain, no benchmark plugin, no new
  test runner.
- The Bronze writer question is neither reopened nor foreclosed.
- No catalog, database, MinIO or Kafka access. The script measures pure functions
  over synthetic data.
- `04-09` is not started. If profiling surfaces a production-relevant defect that
  would need `iceberg/` changed, the work **stops** and the finding is carried to
  a separate authorisation rather than widening this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `verification-contract`: adds a requirement that an optimisation is justified
  against a measured baseline rather than an absolute number. The existing rules
  govern whether a check ran and whether it can fail; none of them governs what a
  measurement may be used to conclude. That gap is exactly what this change runs
  into — a boundary cost measured honestly, with no measured cycle to express it
  as a share of — and the rule is what makes `NOT WORTH DOING (unmeasurable
  baseline)` the correct terminal outcome instead of a judgement call.

## Impact

- `scripts/profile_arrow_boundary.py` — new.
- `artifacts/phase-04/04-arrow-boundary-profile.json` — new. Note that
  `artifacts/` is gitignored and its evidence is tracked by force-add, so the
  artifact needs `git add -f` to survive the commit.
- `docs/adr/0002-steady-state-shadow-policy.md` — one added cross-reference note.
- `openspec/specs/verification-contract/spec.md` — one added requirement.
- No file under `iceberg/`, `spark/`, `dags/` or `dbt/` is touched.
- Requirements addressed: PRF-01, REGR-1, REGR-3.
