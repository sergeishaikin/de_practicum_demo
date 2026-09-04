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
- [ ] Open the pull request against `main`, and record head SHA, base branch,
      base SHA and every required check's run id.

## Milestone 2 — conformance (requires its own authorisation)

- [ ] Convert `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` to `workflow_call` +
      `workflow_dispatch` + path-filtered `pull_request`; remove the
      branch-pinned `push` triggers.
- [ ] Compose the capability workflows from the orchestrating workflows so each
      acceptance exists as one definition.
- [ ] Confirm the Milestone 1 fitness functions turn green for the reason
      intended, and not because an assertion was relaxed.
- [ ] Apply `main` protection: no direct push, no force push, no deletion,
      required status checks, required conversation resolution, branch up to
      date before merge.
- [ ] Disable merge-commit and rebase merging; leave squash merging enabled.
- [ ] Enable `delete_branch_on_merge`.
- [ ] Prove the lifecycle end to end on a canary branch: base SHA, head SHA,
      pull request number, required check names, all required checks green on
      the merge candidate, merge SHA, `main` verification run id, and source
      branch absent after merge.
- [ ] Prove the negative cases: direct push to `main` rejected; merge blocked
      on a failing required check; out-of-date branch blocked; fitness function
      red when a working-branch name is reintroduced into a capability
      workflow.
- [ ] Record every receipt by immutable identity — SHA, run id, artifact
      digest, pull request number — with the base branch and base SHA recorded
      alongside each `pull_request` run.
- [ ] Add the deferred evidence-shape fitness function: evidence citing a
      `pull_request` run records its base branch and base SHA. Deferred from
      Milestone 1 deliberately — the receipt format it would check is settled
      by the Milestone 2 lifecycle proof, and a checker written against an
      unsettled format would assert on prose rather than on a contract.

## Explicitly out of scope

- [ ] NG-0.6 adoption, archival, or any commit touching `feature/ng-0.6-loki`,
      `closure/ng-0.6-loki` or NG-0.6 governance artifacts. Contested state
      under another session; frozen by operator decision on 2026-09-04.
- [ ] Carrying `de68270` (NG-0.6 lifecycle-safe test repair) into this change.
- [ ] Deleting any branch. Cleanup follows Milestone 2 as a separate authorised
      step, because `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` still name two
      of the deletion candidates, and `test/dbt-extensive-testing` is the base
      of pull requests whose receipts are currently cited.
