# Tasks: propagate-development-workflow-contract

## Authorised 2026-09-05

- [x] Verify branch, worktree, remotes and local-vs-remote `main` before any
      state-changing step.
- [x] Measure the propagation gap directly against `main` rather than
      inferring it, and record the per-document result in `design.md`.
- [x] Write the `development-workflow` capability delta adding **The
      integration contract is stated where authors read it**.
- [x] Add the `## Development workflow` section to `AGENTS.md`, stating the
      branch, base, pull-request, divergence, closure, deletion and evidence
      rules, and the pre-implementation ancestry check.
- [x] Correct `AGENTS.md`'s **Planning methodology** enumeration: name the
      three process capabilities and their distinct responsibilities, and stop
      enumerating the platform capabilities inline so the list cannot rot
      again.
- [x] Add `### Git and integration workflow` to `CLAUDE.md` as an operational
      preflight, pointing at `AGENTS.md` and the canonical spec rather than
      restating the requirements.
- [x] Correct `CLAUDE.md`'s **Repository location** section, which directed the
      reader to a checkout that sits on a recorded exception branch, to record
      that the container holds several worktrees and that the branch must be
      confirmed.
- [x] Replace `docs/DEVELOPMENT.md`'s **Branch conventions** and **PR process**
      sections with a contributor-facing summary and a link to the canonical
      spec.
- [x] Inspect `2af84fdf` on the stale `governance/branch-closure-rule` branch,
      which was cut from `d031679` and is not mergeable. Carry forward only the
      branch/worktree Definition-of-Done semantics not already covered by
      **Integrated branches are deleted automatically** — worktree removal,
      the dirty-worktree safety rule, tag-over-branch for historical pointers,
      cleanup-before-next-item, and cleanup status in the handoff — as a second
      capability requirement plus its `AGENTS.md` and `CLAUDE.md` statements.
      Do not merge the branch.
- [x] Extend `tests/test_development_workflow_contract.py` with the
      propagation rules, matching on normalised text, and pair each new
      detector with a synthetic-violation test so no absence rule can pass
      vacuously.
- [x] Prove the new rules bite by running the detector against the pre-change
      tree and recording every finding it reports.
- [x] Run the completion gate: `ruff check .`, `black --check .`, `mypy`,
      `pytest`, and the `iceberg` coverage gate.
- [x] Open the pull request against `main`, and record head SHA, base branch,
      base SHA and every required check's run id in `evidence.md`. PR #15,
      merged `b0102e06`.
- [x] Promote the capability delta into
      `openspec/specs/development-workflow/spec.md` and archive this change,
      once the pull request has integrated.
- [x] Remove the change's worktree and delete its local and remote branches.

## Explicitly out of scope

- [ ] `README.md`'s architecture diagram, medallion description and
      resource-profile table. Separately identified defects; not
      integration-contract defects.
- [ ] Deleting `feature/ng-0.6-loki` or `test/dbt-extensive-testing`, and
      editing the capability's **Recorded exceptions** table. NG-0.6 adoption
      integrated as #14 on 2026-09-04 and may satisfy both end conditions;
      confirming that and re-anchoring the NG-0.6 evidence is its own change.
- [ ] The deferred evidence-shape fitness function (evidence citing a
      `pull_request` run records its base branch and base SHA). Owned by the
      archived `standardize-trunk-based-development` change, where it is
      recorded as blocked on NG-0.6.
- [ ] Adding `CONTRIBUTING.md` or `.github/PULL_REQUEST_TEMPLATE.md`. Rejected
      in `design.md` rather than deferred.
