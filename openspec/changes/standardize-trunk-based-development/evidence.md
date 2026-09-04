# Evidence: standardize-trunk-based-development

## Milestone 1 — preflight

Verified before any state-changing step, on 2026-09-04:

- `origin/main` at `e697f30525ada3b909b49f1cf7c7f699cce69851`.
- Worktree `ng-workflow` created from `origin/main`; branch
  `feat/standardize-trunk-based-development`; clean status at creation.
- `origin/feature/ng-0.6-loki` at `f2bfb929b234019d1efb1a44bd7d6b7087feab5a`
  and untouched by this change.

The Loki branch advanced twice during the session that opened this change —
`1013876` → `7d70f28` → `f2bfb92` — which is why the preflight records its SHA
rather than its name. NG-0.6 is frozen by operator decision and this change
neither reads from nor writes to it.

## Milestone 1 — measured repository state

Every value in `design.md`'s evidence table was measured directly. The two
load-bearing ones:

- Run `33890376252`: `event: pull_request`, `headSha:
  de68270ad3bb5c993af5e35479115cf8aae1d733`, `conclusion: success`,
  `workflowName: CI`. The pull request supplying its merge commit was #6, whose
  base was `test/dbt-extensive-testing` at `9d62da4`, fifteen commits behind
  `main`. The run passed; it is not evidence about `main`.
- Pull requests #5, #6 and #7 all had head `feature/ng-0.6-loki` and base
  `test/dbt-extensive-testing`, and all three are `CLOSED` without merge.

## Milestone 1 — fitness function behaviour

`uv run --locked pytest tests/test_development_workflow_contract.py -q`

```
...xx..
5 passed, 2 xfailed in 0.66s
```

The two xfails are `test_standing_ci_does_not_name_working_branches` and
`test_capability_workflows_declare_workflow_call`, both `strict=True`. They
encode the rules Milestone 2 satisfies. Because they are strict, the suite
fails if either starts passing while its marker is still present, so the
exemption cannot outlive the violation.

The rules that already hold are asserted normally and pass:
`test_capability_workflows_retain_workflow_dispatch` (the exact-SHA escape
hatch exists today, so Milestone 2's conversion cannot silently drop it) and
`test_no_workflow_triggers_on_a_non_main_push`, which asserts the current
violation set by equality rather than by absence.

Three tests exist only to keep the others honest:
`test_workflow_trigger_parsing_survives_the_yaml_on_keyword` (YAML 1.1 resolves
a bare `on` key to the boolean `True`; a detector that missed this would report
zero violations and pass every rule vacuously),
`test_capability_workflows_are_discovered`, and
`test_working_branch_detector_reports_the_known_violations`.

## Milestone 1 — completion gate

Run in the `ng-workflow` worktree at head
`e697f30525ada3b909b49f1cf7c7f699cce69851` plus this change's working tree:

```
uv run --locked ruff check .      All checks passed!
uv run --locked black --check .   111 files would be left unchanged
uv run --locked mypy              Success: no issues found in 10 source files
uv run --locked pytest -q         603 passed, 1 skipped, 81 deselected, 2 xfailed
```

## Milestone 1 — CI receipts

Recorded after the pull request is opened, against base `main`. Each entry
records head SHA, base branch, base SHA, workflow name and run id, per the
requirement this change introduces.

<!-- Pending: no CI receipt is claimed for this change until the pull request
     has run against base `main`. -->

## Not claimed

- No repository setting has been changed. Protection, merge modes and
  `delete_branch_on_merge` are specified in the capability delta and applied in
  Milestone 2.
- No workflow has been modified. The branch-pinned triggers in
  `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` are unchanged, which is why the
  two rules are xfailed rather than passing.
- No branch has been deleted.
- No NG-0.6 artifact has been read into or written from this change.
