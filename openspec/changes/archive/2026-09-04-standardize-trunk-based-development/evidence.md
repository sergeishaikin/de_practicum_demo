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

Pull request #8. Each entry records head SHA, base branch, base SHA, workflow
name, run id and conclusion, in the shape this change's receipt requirement
demands — the base is recorded so that a reader can tell which merge was
verified without reconstructing the pull request.

| Field | Value |
| --- | --- |
| Pull request | #8 |
| Head SHA | `03416c6c050008f96d0b936af1d371b8f11d2680` |
| Base branch | `main` |
| Base SHA | `e697f30525ada3b909b49f1cf7c7f699cce69851` |

| Workflow | Event | Run id | Conclusion |
| --- | --- | --- | --- |
| CI | `pull_request` | `33901538965` | success |
| M5 architecture gates | `pull_request` | `33901538879` | success |

All five required checks passed on that head against that base: Lint + compose
validation (31s), Unit tests + coverage (33s), Warehouse dbt contract +
artifacts (1m20s), PR M3/M4 recovery and cutover gates (2m0s), Airflow DAG
validation (3m53s). `main` was at `e697f30` when the runs executed and is
unchanged at the time of recording, so the verified merge candidate is the one
that would integrate.

The unit test job ran the two strict xfails without an `XPASS`, which is the
observable confirmation that the branch-name and `workflow_call` rules are
still violated in CI as well as locally — the violation is a property of the
repository, not of the local checkout.

### Which head a receipt belongs to

`03416c6` is this change's implementation head. Commits after it are
receipt-recording and documentation only, and each one necessarily produces a
new head with its own runs — writing a receipt into the repository moves the
thing the receipt describes.

That recursion terminates at the pull request, not in this file, because the
two serve different purposes:

| | Historical evidence (this file) | Merge-time authority (the pull request) |
| --- | --- | --- |
| Records | candidate head SHA, tested base branch, tested base SHA, run ids | final head, current integration state, required checks, branch protection |
| Answers | what was verified, and against what | whether this may integrate now |
| Ages | yes — both head and base | no — re-evaluated against `main` as it is |

Both SHAs recorded here go stale. The head ages the moment the document is
committed, and the recorded base ages too if `main` advances before merge; a
receipt against `e697f30` says nothing about integrating into a `main` that has
since moved. Neither is a defect, because this file is an audit trail and not a
merge gate.

The blocking gate is GitHub's required checks on the final merge candidate,
which are re-evaluated against `main` as it actually is. What this file
contributes is the record of which merge was verified — and that is why the
requirement obliges evidence to name the base at all. Run `33890376252` had a
perfectly good head SHA; recording its base is what would have shown, without
opening the pull request, that the run was about a merge into
`test/dbt-extensive-testing` and therefore could not support adoption.

## Not claimed

- No repository setting has been changed. Protection, merge modes and
  `delete_branch_on_merge` are specified in the capability delta and applied in
  Milestone 2.
- No workflow has been modified. The branch-pinned triggers in
  `ci-ng05-tempo.yml` and `ci-ng06-loki.yml` are unchanged, which is why the
  two rules are xfailed rather than passing.
- No branch has been deleted.
- No NG-0.6 artifact has been read into or written from this change.

## Milestone 2 — workflow conformance

Pull request #10, head `b6bcc38`, base `main` at `8521a08`, merged as `3f41692`.

All twelve jobs across seven workflows passed. The set that ran is itself the
evidence for the self-reference fix: `H1 clean reproducible stack`
(`33905344104`, 13m8s and 12m20s), `NG-0.5 Tempo capability` (`33905344081`,
1m52s) and `NG-0.6 Loki capability` (`33905344092`, 3m44s) executed **because
their own definitions changed**. Before this change, editing those three files
triggered nothing, and they are precisely the three workflows carrying
acceptance claims.

Also green: `CI` (`33905344057`), `M5 architecture gates` (`33905344074`),
`Metadata profile` (`33905344087`, 11m35s), `S1 dbt semantic lineage`
(`33905344064`).

## Milestone 2 — repository settings

Applied 2026-09-04 and read back from the API rather than assumed.

| Setting | Before | After |
| --- | --- | --- |
| `allow_merge_commit` | `true` | `false` |
| `allow_rebase_merge` | `true` | `false` |
| `allow_squash_merge` | `true` | `true` |
| `delete_branch_on_merge` | `false` | `true` |
| `main` protected | `false` | `true` |
| `required_status_checks.strict` | — | `true` |
| `enforce_admins` | — | `true` |
| `allow_force_pushes` | — | `false` |
| `allow_deletions` | — | `false` |
| `required_conversation_resolution` | — | `true` |
| `required_approving_review_count` | — | `0` |

Required contexts, deliberately limited to the four jobs that run on every pull
request:

```
Lint + compose validation
Unit tests + coverage
Warehouse dbt contract + artifacts
Airflow DAG validation
```

Path-filtered gates are **not** required checks. A required context that never
reports leaves a pull request permanently unmergeable, so requiring
`M5 architecture gates` or `H1 clean reproducible stack` would deadlock any
change that does not touch their paths. Requiring them needs the aggregating
`if: always()` gate job, which belongs to the impact-router change.

## Milestone 2 — negative cases against live protection

Executed against `main` at `3f4169245bb6a34873383ad244e53913d689a1d1`, from a
detached worktree, by the repository owner — who is an admin, which is what
makes `enforce_admins: true` observable rather than asserted.

| Case | Command | Exit | Server response |
| --- | --- | --- | --- |
| Direct push | `git push origin HEAD:main` | `1` | `GH006: Protected branch update failed` — "Changes must be made through a pull request", "4 of 4 required status checks are expected" |
| Force push | `git push --force origin HEAD:main` | `1` | `GH006: Protected branch update failed` |
| Branch deletion | `git push origin :main` | `1` | "refusing to delete the current branch: refs/heads/main" |

`main` remained at `3f41692` throughout.

One honest distinction: the deletion refusal cites the default-branch rule, not
the protection rule. `allow_deletions: false` is set and read back, but the
default-branch guard answers first, so this receipt proves deletion is refused
without isolating which of the two mechanisms refused it.

## Milestone 2 — `workflow_call` proved behaviourally

Declaring `workflow_call` proves only that the declaration parses. The called
path was proved by dispatching the permanent orchestrator, twice.

**Negative first.** Run `33907911886`, `workflow_dispatch` on `main`, with a
stale `expected_sha` (`3f41692`, the previous `main`):

```
dispatched ref resolved to 261a4c5453c37d8f05b613a62774338f56943446
but the operator expected 3f4169245bb6a34873383ad244e53913d689a1d1

Verify the dispatched ref resolves to the intended SHA : failure
NG-0.6 Loki capability (called)                        : skipped
NG-0.5 Tempo capability (called)                       : skipped
```

The callee was **skipped**, not executed and ignored. A mismatch between
operator intent and resolved ref stops the capability from running at all, so
this path cannot produce a receipt against a commit nobody named — which is the
class of defect that produced run `33890376252`.

**Positive.** Run `33907950450`, `workflow_dispatch` on `main`,
`capability: ng06-loki`, `expected_sha: 261a4c5453c37d8f05b613a62774338f56943446`:

| Link in the chain | Value | Source |
| --- | --- | --- |
| Operator intent | `261a4c5453c37d8f05b613a62774338f56943446` | `expected_sha` input |
| Dispatcher resolved ref | `261a4c5453c37d8f05b613a62774338f56943446` | run `33907950450` `head_sha`, asserted equal in preflight |
| Callee checkout `HEAD` | `261a4c5453c37d8f05b613a62774338f56943446` | job `101137305273` `head_sha`, with step 6 `Verify exact implementation SHA` (`test "$(git rev-parse HEAD)" = "$GITHUB_SHA"`) concluding `success` |
| Called capability execution | run `33907950450`, job `101137305273` | `NG-0.6 Loki capability (called) / capability`, conclusion `success` |

One honest note on the fourth row: a called workflow does **not** receive its
own run id. Its jobs execute inside the caller's run, so the durable identity
of the called capability is the caller run id plus the job id, not a separate
run. Recording only "the capability ran" without the job id would leave nothing
to open.

## Milestone 2 — lifecycle proof

| Event | Value |
| --- | --- |
| Base at branch creation | `3f4169245bb6a34873383ad244e53913d689a1d1` |
| PR #11 head / merge | `3326ba2` → squash `20469d58a3923d8845c5ac84887a5603e4eaee64` |
| PR #12 head / merge | `ea72486af808e4e9f8199415dd51c64c1b991b3d` → squash `261a4c5453c37d8f05b613a62774338f56943446` |
| Required checks | Lint + compose validation, Unit tests + coverage, Warehouse dbt contract + artifacts, Airflow DAG validation |
| PR #11 checks | run `33907052341` (4 jobs) and `33907052290`, all `success` |
| PR #12 checks after update | run `33907581457`, all four `success` |
| Branch after merge | `GET /git/ref/heads/feat/capability-dispatch` → `404`; `GET /git/ref/heads/docs/m2-evidence-shape-dependency` → `404` |

Neither merge passed `--delete-branch`; the branches were removed by
`delete_branch_on_merge`. Both merges were squash — merge-commit and rebase
merging are disabled, so no other mode was available.

### The `strict: true` proof, as a single-event transition

PR #12 was branched from `main` at `3f41692` **before** PR #11, so one merge
moved its base while nothing about the pull request itself changed.

| | `main` | PR #12 head | `mergeable` | `mergeable_state` |
| --- | --- | --- | --- | --- |
| Before | `3f41692` | `3269f5f` | `MERGEABLE` | `CLEAN` |
| After merging #11 | `20469d5` | `3269f5f` | `MERGEABLE` | `BEHIND` |

Its four required checks were green before and stayed green; only the base
moved. The merge was then refused:

```
gh pr merge 12 --squash
  exit 1
  "Pull request #12 is not mergeable: the head branch is not up to date with the base branch."
```

`mergeable: true` with `mergeable_state: behind` is the distinction that
matters: the merge is conflict-free and still forbidden until the branch is
updated to the current protected base. A settings read-back of `strict: true`
could not have shown this. `PUT /pulls/12/update-branch` moved the head to
`ea72486` and the state returned to `BLOCKED` on re-triggered checks, then
`CLEAN`.

### Negative case not run

`gh` offered `--admin` to force the out-of-date merge. It was not attempted.
`enforce_admins: true` is already proved on the stronger vector — an admin's
direct push rejected — and deliberately testing a bypass of newly installed
protection has an irreversible outcome if it unexpectedly succeeds. Covering
that vector belongs on a disposable branch as its own test.

## Milestone 2 — final topology assertion

Read from the API after cleanup, at `main` = `261a4c5`:

```
permanent:
  main                                    protected = true

temporarily retained by recorded exception:
  feature/ng-0.6-loki                     9 ahead of main
  test/dbt-extensive-testing              11 ahead of main

legacy branches, asserted absent:
  feature/ng-0.4-otel                     deleted
  feature/ng-0.5-tempo                    deleted
  feature/prometheus-trace-exemplars      deleted
  integration/ng-0.5                      deleted
```

Each deleted branch was verified `0` commits ahead of `main` and
`merge-base --is-ancestor origin/<branch> origin/main` returned true
immediately before deletion, so every commit they named remains reachable from
`main` and no recorded claim was orphaned.

The two retained branches are registered as exceptions in the standing
capability with their reasons and the conditions that end them. Both are
consequences of the same unresolved change and both close with it. They are not
residue of the old topology left unexamined.

Note that `test/dbt-extensive-testing` was `0` ahead of `main` when this change
began and is now `11` ahead; `feature/ng-0.6-loki` moved from `1013876` to
`89a44bc` across the same period. Both are under active work by another
session. That is a further reason the exception is recorded rather than
resolved here.
