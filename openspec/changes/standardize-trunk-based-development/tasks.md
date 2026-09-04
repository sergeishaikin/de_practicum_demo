# Tasks: standardize-trunk-based-development

## Milestone 1 — contract and fitness functions (authorised)

- [x] Verify branch, worktree, remotes and local-vs-remote `main` before any
      state-changing step.
- [x] Measure the current repository state directly — protection, rulesets,
      merge modes, `delete_branch_on_merge`, fork relationship, branch
      divergence, workflow triggers, validation pull requests and the cited
      receipt — and record the measured values in `design.md`.
- [x] Write the `development-workflow` capability delta.
- [x] Add executable fitness functions under `tests/` for the
      repository-visible rules: no working-branch names in standing CI
      definitions, no `push` trigger on a non-`main` branch, capability
      workflows declare `workflow_call`, and capability workflows retain
      `workflow_dispatch`. Each rule is paired with a test that proves its
      detector is not vacuous.
- [x] Record that the branch-name and `workflow_call` fitness functions fail on
      `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` at Milestone 1, with the exact
      failure output, as the evidence that the rules bite before anything is
      changed to satisfy them.
- [x] Run the completion gate: `ruff check .`, `black --check .`, `mypy`,
      `pytest`.
- [x] Open the pull request against `main`, and record head SHA, base branch,
      base SHA and every required check's run id.

## Milestone 2 — conformance (authorised 2026-09-04)

- [x] Convert `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` to `workflow_call` +
      `workflow_dispatch` + path-filtered `pull_request`; remove the
      branch-pinned `push` triggers.
- [x] Declare `workflow_call` on every capability gate, not only the two that
      were branch-pinned. The requirement is on capability workflows as a
      class; `ci-h1-clean`, `ci-m5-gates`, `ci-metadata` and `ci-s1-dbt` were
      found missing it by the fitness function, which is wider than the
      Milestone 2 plan anticipated.
- [x] Add the missing gate self-references so a pull request cannot edit an
      acceptance gate's own definition without triggering it. `ci-h1-clean`,
      `ci-ng05-tempo` and `ci-ng06-loki` lacked it; `ci-m5-gates`,
      `ci-metadata` and `ci-s1-dbt` already had it.
- [x] Confirm the Milestone 1 fitness functions turn green for the reason
      intended, and not because an assertion was relaxed. Replace the
      known-violation guards with synthetic-violation guards so each absence
      rule stays non-vacuous once the repository conforms.
- [x] Pin the branch-deletion rule in the capability: deletion is a consequence
      of successful integration, never a cause of evidence loss; claims are
      anchored to immutable identity before any branch is deleted.
- [x] Apply `main` protection: no direct push, no force push, no deletion,
      required status checks, `strict: true`, required conversation
      resolution, `enforce_admins: true`.
- [x] Require only the four always-running `ci-pr.yml` contexts. Path-filtered
      gates SHALL NOT be required checks until the aggregating gate job exists,
      because a required context that never reports leaves the pull request
      permanently unmergeable.
- [x] Disable merge-commit and rebase merging; leave squash merging enabled.
- [x] Enable `delete_branch_on_merge`.
- [x] Add `ci-capability-dispatch.yml`, a permanent manual orchestrator that
      invokes a capability gate through `uses:` and owns the exact-SHA target
      contract, so the `workflow_call` path can be proved without opening a
      pull request nobody intends to merge.
- [ ] Prove `workflow_call` behaviourally, not by declaration: dispatch the
      orchestrator with an `expected_sha`, and show the caller's resolved SHA
      and the callee's `git rev-parse HEAD` are that same commit. A green
      `pull_request` run proves only that the declaration parses and the
      pull-request path still works.
- [ ] Prove the lifecycle end to end on a canary branch: base SHA, head SHA,
      pull request number, required check names, all required checks green on
      the merge candidate, merge SHA, `main` verification run id, and source
      branch absent after merge.
- [ ] Prove the negative cases, each producing a receipt rather than a claim:
      direct push to `main` rejected; merge blocked on a failing required
      check; merge-commit and rebase merging unavailable; fitness function red
      when a working-branch name is reintroduced into a capability workflow.
- [ ] Prove the out-of-date case against real base movement: a disposable
      branch whose pull request is green, then advance `main` independently,
      and show GitHub reports the pull request as **not mergeable until the
      branch is updated to the current protected base**. A settings read-back
      of `strict: true` is not this proof; the property is behavioural.
- [ ] Delete only the fully subsumed, dependency-free branches:
      `feature/ng-0.4-otel`, `feature/ng-0.5-tempo`,
      `feature/prometheus-trace-exemplars`, `integration/ng-0.5`. Anchor any
      claim that names them to immutable identity first.
- [ ] Record every receipt by immutable identity — SHA, run id, artifact
      digest, pull request number — with the base branch and base SHA recorded
      alongside each `pull_request` run.
- [ ] Promote the capability to `openspec/specs/development-workflow/` and
      archive this change, only once the repository conforms. Not at Milestone
      1: `engineering-governance` requires a standing capability to describe
      present behaviour, and until this milestone lands the repository
      knowingly violates it.
- [ ] Add the deferred evidence-shape fitness function: evidence citing a
      `pull_request` run records its base branch and base SHA. **Blocked on
      NG-0.6, not on effort.** The receipt format is now settled by this
      change's own Milestone 2 records, but the only other evidence file on
      `main` that cites `pull_request` runs is
      `openspec/changes/add-loki-log-backend/evidence.md`, which records no
      base at all — it is the motivating defect, and it is frozen. A checker
      written today would either fail on a file this change is fenced out of
      touching, or carry a named exemption for it. An exemption list that
      exists to excuse the one file the rule was written for is worse than no
      checker: it encodes the defect as permitted. This lands after NG-0.6
      resolves and its evidence is re-anchored.

## Deferred to the impact-router change

- [ ] Compose the capability workflows from an orchestrating workflow so each
      acceptance is invoked rather than restated. Declaring `workflow_call`
      unblocks this; performing it requires the changed-files impact router and
      the aggregating gate job, which are the existing CI backlog item and not
      this change's fence.

## Explicitly out of scope

- [ ] NG-0.6 adoption, archival, or any commit touching `feature/ng-0.6-loki`,
      `closure/ng-0.6-loki` or NG-0.6 governance artifacts. Contested state
      under another session; frozen by operator decision on 2026-09-04.
- [ ] Carrying `de68270` (NG-0.6 lifecycle-safe test repair) into this change.
- [ ] Deleting any branch. Cleanup follows Milestone 2 as a separate authorised
      step, because `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` still name two
      of the deletion candidates, and `test/dbt-extensive-testing` is the base
      of pull requests whose receipts are currently cited.
