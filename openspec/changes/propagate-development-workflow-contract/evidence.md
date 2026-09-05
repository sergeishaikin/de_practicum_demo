# Evidence: propagate-development-workflow-contract

## Preflight

Verified before any state-changing step.

- `main` and `origin/main` both at `acbce84` when the branch was cut on
  2026-09-04; both at `978863d` after `Adopt NG-0.6 Loki capability,
  re-derived from main (#14)` integrated.
- Worktree `docs-workflow-align` created from `main`; branch
  `docs/align-development-workflow-contract`; clean status at creation;
  `git merge-base --is-ancestor main HEAD` confirmed before the first edit.
- The branch was rebased onto `978863d` when `main` advanced mid-change, and
  the ancestry check was re-run rather than assumed. The change is stated
  against `978863d`.

The preflight is recorded because this change exists to make it mandatory. It
was run here by following the procedure being written, which is the weakest
possible form of the guarantee — the fitness function, not the discipline, is
what makes it repeatable.

## Measured propagation gap

The detector added by this change, run against `main` at `978863d` with the
three documents extracted by `git archive`. Eleven findings:

```text
AGENTS.md: does not cite openspec/specs/development-workflow/spec.md
AGENTS.md: does not state that branches originate from current main
AGENTS.md: does not state that pull requests target main
CLAUDE.md: does not cite openspec/specs/development-workflow/spec.md
CLAUDE.md: does not state that branches originate from current main
CLAUDE.md: does not state that pull requests target main
docs/DEVELOPMENT.md: does not cite openspec/specs/development-workflow/spec.md
docs/DEVELOPMENT.md: does not state that branches originate from current main
docs/DEVELOPMENT.md: does not state that pull requests target main
docs/DEVELOPMENT.md: still claims: 'no explicit convention is documented'
docs/DEVELOPMENT.md: still claims: 'no pull-request template or review workflow is defined'
```

Against this branch the same detector reports `clean`.

This is the evidence that the rules bite. A propagation checker that had only
ever been run against a conforming tree would be indistinguishable from one
whose matcher never fires.

## Non-vacuity of the new rules

Both absence rules are paired with synthetic-violation tests, following the
convention already established in this module:

- `test_propagation_detector_reports_a_synthetic_violation` builds three
  documents in `tmp_path` — one conforming, one omitting the branch-origin
  rule, one stating both rules but still carrying a falsified claim — and
  asserts the detector reports exactly the second and third.
- `test_propagation_detector_reports_a_missing_document` asserts that a
  renamed or deleted target fails as `missing` rather than passing vacuously.
- `test_the_canonical_spec_is_where_every_document_points` asserts the spec
  file exists and still contains its **Recorded exceptions** table, because
  three documents now send readers to it.

## Motivating incident

| | |
|---|---|
| Branch | `feature/ng-0.7-grafana-correlation` |
| Base it was created from | `d031679` (tip of `test/dbt-extensive-testing`) |
| Commit made on that base | `9882d98`, pushed to `origin` |
| `main` at the time | `acbce84`; `d031679` was 11 ahead / 7 behind, with `main` not an ancestor |
| Requirement breached | Implementation branches originate from current `main` |
| Repair | `git rebase --onto main d031679`; `9882d98` → `cc2c16d`; patch verified byte-identical; force-pushed with `--force-with-lease` on 2026-09-05 |

The repair is recorded by immutable identity as the incident that motivated
this change. It produced no commit on this branch and is not claimed as this
change's work.

## Carried-forward branch, by immutable identity

| | |
|---|---|
| Branch | `governance/branch-closure-rule` (remote only) |
| Commit | `2af84fdfc023e0dcfcbba55d731416c7f1ae7d26` |
| Parent | `d031679` — the legacy baseline; `main` is not an ancestor |
| Files | `AGENTS.md` (+29), `CLAUDE.md` (+1) |
| Disposition | not merged; semantics re-derived onto `main` as the **Closure includes branch and worktree cleanup** requirement |

Verified with `git merge-base --is-ancestor main 2af84fd`, which reports that
`main` is **not** an ancestor. The branch is deleted in the cleanup step; this
row is its durable anchor.

## Completion gate

Run on this branch against `main` at `978863d`.

| Check | Result |
|---|---|
| `uv run --locked ruff check .` | All checks passed |
| `uv run --locked black --check .` | 111 files would be left unchanged |
| `uv run --locked mypy` | Success: no issues found in 10 source files |
| `uv run --locked pytest` | 619 passed, 1 skipped, 81 deselected |
| `pytest tests --cov=iceberg --cov-fail-under=90` | Required coverage reached — 92.62% |
| `pytest tests/test_development_workflow_contract.py` | 19 passed (14 pre-existing, 5 added) |

No Compose, runtime or dependency surface changed, so the change-specific gates
for those surfaces do not apply. No live-stack check was skipped, because none
is applicable to this change.

## Pending

- Pull request against `main`: head SHA, base branch, base SHA and required
  check run ids to be recorded here once opened. A `pull_request` run verifies
  the merge of head into base, so the base is recorded alongside the head —
  the requirement this capability added after a receipt was cited without one.
- Promotion of the capability delta into
  `openspec/specs/development-workflow/spec.md` and archival of this change,
  after integration.
