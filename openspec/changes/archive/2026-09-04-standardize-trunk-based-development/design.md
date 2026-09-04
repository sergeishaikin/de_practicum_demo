# Design: standardize-trunk-based-development

## Evidence base

All facts below were measured against the repository on 2026-09-04, not taken
from an earlier analysis.

| Observation | Measured value |
| --- | --- |
| `main` protection | `protected: false`, `rulesets: []` |
| Merge modes | merge commit, squash and rebase all enabled |
| `delete_branch_on_merge` | `false` |
| Fork parent | `dim4eg91/de_practicum_demo` |
| `origin/main` vs `upstream/main` | 389 ahead, 0 behind |
| Branches `0` ahead of `main` | `feature/ng-0.4-otel` (65 behind), `feature/ng-0.5-tempo` (35), `feature/prometheus-trace-exemplars` (59), `integration/ng-0.5` (17), `test/dbt-extensive-testing` (15) |
| Workflows declaring `workflow_call` | none of 9 |
| Workflows naming a working branch | `ci-ng05-tempo.yml`, `ci-ng06-loki.yml` |
| Validation-only pull requests | #5, #6, #7 — all head `feature/ng-0.6-loki`, all base `test/dbt-extensive-testing` (`9d62da4`), all closed unmerged |
| Cited repair receipt | run `33890376252`, `event: pull_request`, `headSha: de68270`, conclusion `success`, base `test/dbt-extensive-testing` |

## The defect that motivates the receipt requirement

The NG-0.6 closure evidence cites run `33890376252` as proof that the
lifecycle-safe test repair is green. The run is real and it succeeded. Its
`pull_request` event, however, verified the merge of `de68270` into
`test/dbt-extensive-testing` — a branch fifteen commits behind `main`.

GitHub's `pull_request` event builds the merge of head into **base**. The
receipt therefore proves that the repair integrates cleanly into a branch it
will never integrate into, and says nothing about `main`. Nothing in the
receipt's own text reveals this: it records the head SHA and the merge SHA, and
a reader who does not open the pull request cannot tell which base produced it.

This is why the requirement is written as "prove the candidate against its real
integration base" rather than as "do not open pull requests against `test/*`".
Banning a branch prefix would forbid one route to the defect. Requiring the
base to be the integration target forbids the defect itself, and the added
obligation to record the base alongside the head makes the violation visible in
the evidence rather than only in GitHub's API.

## Decisions

**Elapsed branch age is a signal, not a gate.** Wall-clock age is a weak proxy
for the invariant that actually matters — small divergence from `main`. A
healthy pull request opened on a Friday should not become invalid on Monday.
The requirement therefore records a three-day target and a seven-day rationale
threshold, and the fitness function does not fail on age.

**The merge requirement is stated on history, not on GitHub's button.** Naming
"squash merge" in a standing capability couples the contract to one hosting
provider's vocabulary. The requirement states that integration produces one
durable logical change on `main`; squash merge is recorded as the current
implementation of that.

**`main` may be named in workflows; working branches may not.** `main` is
permanent by the first requirement, so naming it cannot rot. This keeps the
fitness function precise: it fails on `ci-ng05-tempo.yml` and `ci-ng06-loki.yml`
while leaving the legitimate `branches: [main]` triggers in `ci-pr.yml`,
`ci-integration.yml` and `ci-s1-dbt.yml` alone.

**Composition over duplication.** The alternative to `workflow_call` — copying a
gate's step sequence into each workflow that needs it — would satisfy "invocable
without a pull request" while creating two definitions of one gate that can
drift apart. The requirement forbids that explicitly.

## Rejected options

**Git Flow (`develop`, `release/*`, `hotfix/*`).** Adds a second permanent
integration line and a synchronisation obligation between it and `main`. The
project has one delivery train, continuous verification and OpenSpec-based
authorisation; `develop` would add merge complexity without addressing any
observed problem. It would also worsen the specific failure here, which is
already caused by too many long-lived lines rather than too few.

**Enforcing branch age in CI.** Rejected above: it fails healthy work and does
not catch the real fault, which is unbounded scope rather than elapsed time.

**Banning `test/*` and `integration/*` branch names outright.** Rejected as
both too broad and too narrow — too broad because a bounded change may
legitimately be named `test/…`, too narrow because the defect is the permanent
lane and the stale base, neither of which is a naming property.

**Absorbing `de68270` into this change.** The NG-0.6 lifecycle-safe test repair
is unmerged and its branch is contested. Carrying it here would be convenient
and would breach this change's own "one branch carries one bounded change"
requirement on the first implementation of that requirement. It stays with
NG-0.6.

## Relationship to existing capabilities

`engineering-governance` governs how work is authorised and fenced;
`verification-contract` governs what counts as verified. Neither says anything
about how a verified change reaches `main`, which is how the branch topology
came to sit inside the verification boundary without ever being specified.
`development-workflow` fills that gap and defers to both: it adds no
authorisation rule and weakens no gate.

The receipt requirement is a strengthening of `verification-contract`'s "A
check is only reported as passed if it was executed". That requirement is
satisfied by run `33890376252` — the check was executed, and it did pass. What
was missing is that the executed check must be the one the claim needs.

## Milestone 2 sequencing (not authorised by this milestone)

The order matters and is not arbitrary:

1. Convert `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` to `workflow_call` +
   `workflow_dispatch` + path-filtered `pull_request`; remove the branch-pinned
   `push` triggers; compose them from the orchestrating workflows.
2. Apply `main` protection, disable merge-commit and rebase merging, enable
   `delete_branch_on_merge`.
3. Prove the lifecycle end to end on a canary branch, and prove the negative
   cases: direct push rejected, merge blocked on a failing required check,
   out-of-date branch blocked, branch-name fitness function red when a branch
   name is reintroduced.
4. Only then delete the subsumed legacy branches.

Deleting branches before step 1 would break the two workflows that name them.
Deleting `test/dbt-extensive-testing` before NG-0.6 is resolved would also
destroy the base of the pull requests whose receipts are currently cited.
