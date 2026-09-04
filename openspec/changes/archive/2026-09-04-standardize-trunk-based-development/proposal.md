# Proposal: standardize-trunk-based-development

## Problem

The repository's verification architecture is more mature than its integration
architecture. Acceptance is evidence-based — exact-SHA receipts, fail-closed
freshness, mutation gates, architectural fitness functions — but the Git
workflow still reflects an earlier exploratory phase, and that mismatch has
begun to damage the evidence itself.

Three concrete symptoms, each verified against the repository rather than
inferred:

- **Branches became project state.** PR #1 carried 212 commits from
  `test/dbt-extensive-testing`; PR #2 carried 162 from `feature/ng-0.4-otel`.
  Those branches stopped representing one change and became alternate versions
  of the whole project. Four branches — `feature/ng-0.4-otel`,
  `feature/ng-0.5-tempo`, `feature/prometheus-trace-exemplars` and
  `integration/ng-0.5` — are now `0` ahead of `main` and retain nothing unique.
- **Branch names are compiled into standing CI.** `ci-ng05-tempo.yml` and
  `ci-ng06-loki.yml` carry `push: branches: [feature/ng-0.5-tempo]` and
  `push: branches: [feature/ng-0.6-loki]`. No workflow in the repository
  declares `workflow_call`, so an acceptance gate cannot be composed; it can
  only be triggered by being on the right branch, or by opening a pull request.
- **A pull request became CI machinery, and that corrupted a receipt.** PRs
  #5, #6 and #7 were validation-only and were all closed without merge. All
  three targeted `test/dbt-extensive-testing` — `9d62da4`, fifteen commits
  behind `main` — rather than the branch the work would actually integrate
  into. The NG-0.6 closure evidence then cited Core CI run `33890376252`
  (`event: pull_request`, `headSha: de68270`) as a repair receipt. That run is
  green, and it proves the repair merges cleanly into a stale legacy branch. It
  does not prove the candidate passes against `main`, which is where the change
  lands.

The last symptom is the important one. This is not untidiness. A receipt that
reads as closure evidence, and is green, and does not support the integration
it is cited for, defeats the purpose of an evidence-based acceptance model. The
branch topology produced that receipt, so the topology is inside the
verification boundary whether or not it was ever specified as such.

`main` is currently unprotected (`protected: false`, no rulesets), all three
merge modes are enabled, and `delete_branch_on_merge` is `false`. For a project
whose stated philosophy is that a claim is only as good as the check that was
executed, an unenforced integration boundary is the largest gap between what
the repository says about itself and what it enforces.

## Proposed bounded change

Make the development workflow a standing, governed capability —
`development-workflow` — rather than an unwritten convention, and bring the
repository into conformance with it.

The capability defines: a single permanent integration branch; branch and pull
request lifecycle; what a pull request means and what it does not; how
verification is invoked without manufacturing a pull request to trigger it;
that an adoption receipt must prove the candidate against its real integration
base; that evidence refers to immutable identity rather than to a branch still
existing; merge and protection semantics for `main`; and the fork/upstream
policy. The rules that can be checked from the repository are checked by
executable fitness functions, not by inspection.

## Non-goals

- No Git Flow, no `develop`, no permanent `release/*`, `integration/*`,
  `test/*` or environment branches.
- No new test framework, task runner, wrapper or verification layer. The
  fitness functions are `pytest` tests under `tests/`, consistent with
  `test_m5_fitness_functions.py` and `test_backlog_validator.py`.
- No change to what the acceptance gates assert. Milestone 2 changes how a gate
  is invoked and composed, never what it verifies.

## Scope fence

- This change SHALL NOT touch `feature/ng-0.6-loki`, `closure/ng-0.6-loki`, or
  any NG-0.6 governance artifact. NG-0.6 adoption is contested state under
  active work by another session; the second revert's reason is unknown and is
  not inferred here. `de68270`'s lifecycle-safe test repair belongs to NG-0.6
  semantics and SHALL NOT be absorbed into this change merely because its
  branch is inconvenient — doing so would breach this change's own
  "one bounded change" requirement on its first implementation.
- This change SHALL NOT delete any branch. Cleanup of the four subsumed
  branches is a separate authorised step after this capability is operational,
  because deleting `feature/ng-0.5-tempo` or `feature/ng-0.6-loki` while
  `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` still name them would leave dead
  triggers.
- This change SHALL NOT alter the assertions of any acceptance gate, or the
  runtime, Compose, Collector, dbt, Airflow or observability configuration.
- Repository settings (protection, merge modes, `delete_branch_on_merge`) are
  specified in Milestone 1 and applied in Milestone 2, not applied ahead of the
  contract that authorises them.
- NG-0.6 remains where the other session leaves it. This change neither adopts
  nor rejects it.

## Milestones

**Milestone 1 — contract (this authorisation).** Write the
`development-workflow` capability delta and the executable fitness functions
that check the repository-visible rules. No CI behaviour changes; no repository
settings change. The branch-name fitness function is expected to fail on the
two branch-pinned workflows, and that failure is the evidence the rule bites.

**Milestone 2 — conformance (requires its own authorisation).** Convert the
capability workflows to `workflow_call` + `workflow_dispatch` + path-filtered
`pull_request`, remove the branch-pinned `push` triggers, compose them from the
orchestrating workflows, then apply `main` protection, squash-only merging and
`delete_branch_on_merge`, and prove the full lifecycle end to end with a canary
branch and the negative cases.
