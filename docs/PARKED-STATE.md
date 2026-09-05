# Parked state — 2026-09-05

This repository was deliberately brought to a stopping point and left. It is not
abandoned and nothing is half-applied: `main` is authoritative, no change is in
flight, and every branch that existed has either integrated or been anchored to
an immutable reference and deleted.

Read this file first when picking the project back up. It records what is true,
what was deliberately left undone, and where to find the work that was parked.

## State at parking

| Property | State |
|---|---|
| `main` | `770a9018c93ad37304f5bc202809d5a612eda09f` |
| Remote branches | `main` only |
| Open pull requests | none |
| Active OpenSpec changes | none — `openspec/changes/` holds `.gitkeep` and `archive/` |
| Backlog lifecycle | 7 `DONE`, 7 `PLANNED`, **0 `ACTIVE`** |
| Recorded spec exceptions | none — the two that existed closed on 2026-09-05 |
| Local worktrees | one, the repository root |
| `main` protection | direct push, force push and deletion rejected; four required checks; `strict: true`; conversation resolution required; `enforce_admins: true` |
| Merge modes | squash only; merge-commit and rebase disabled; `delete_branch_on_merge` enabled |

## What was closed

Five pull requests, each branched from the then-current `main`, verified against
it, squash-merged and auto-deleted.

| PR | Merge | What it closed |
|---|---|---|
| #15 | `b0102e06` | Propagated the `development-workflow` contract into `AGENTS.md`, `CLAUDE.md` and `docs/DEVELOPMENT.md`, which still said no branch convention existed |
| #16 | `249e0bc4` | Adopted the two new requirements into the standing capability and archived the change |
| #17 | `156d320e` | Closed NG-0.6 governance: re-anchored every `pull_request` citation to base branch and base SHA, replaced the merge-time placeholder, rewrote the exceptions table as history, and landed the deferred evidence-shape checker with no exemption list |
| #18 | `ee60a49f` | Archived that closure with its own merge-time receipt |
| #19 | `770a9018` | Rebuilt the README architecture around the platform's real planes, corrected the Iceberg relationship, documented all six Compose profiles, and added the medallion rollout modes |

## Durable anchors

Two tags exist so that deleted branches orphan nothing. Neither is a branch, so
neither reads as active work.

| Tag | Commit | Why it exists |
|---|---|---|
| `ng-0.6-evidence-baseline` | `d031679` | Tip of the deleted `test/dbt-extensive-testing`. The archived NG-0.6 evidence names eleven commits on that line by SHA as Class 1 historical receipts; all eleven are reachable from this tag. Also the base of pull requests #5, #6, #7 and #9, and the parent of `2af84fdf` from the deleted `governance/branch-closure-rule`. |
| `ng-0.7-m1-research` | `cc2c16d` | The sole commit of the deleted `feature/ng-0.7-grafana-correlation`: NG-0.7 Milestone 1 research and design. Milestone 2 was never authorised. |

## Deliberately not done

Each item below is a decision, not an oversight. None is hidden in an archived
task checklist.

### NG-0.7 Milestone 2 — not authorised

Milestone 1 was completed on 2026-09-04. Milestone 2 implementation was never
authorised, and `add-grafana-correlation-slo`'s own `tasks.md` says so. Parking
the project is not an authorisation, so M2 was not started.

The backlog register keeps NG-0.7 at `PLANNED` / `pending` / authorisation
`NONE`, which is its true state. The M1 work is at tag `ng-0.7-m1-research`, and
`openspec/backlog/next-generation/NG-0.7-grafana-correlation.md` records how to
recover it and why it must be re-verified rather than carried forward.

### CI capability composition — deferred to a change that does not exist yet

`standardize-trunk-based-development` deferred one task to an "impact-router
change": composing the capability workflows from an orchestrating workflow so
each acceptance is invoked rather than restated. Declaring `workflow_call`
unblocked it; performing it needs a changed-files impact router and an
aggregating gate job.

**There is no backlog item for it.** The backlog is the next-generation
programme register, and adding a CI item would extend a bounded programme
authorisation — which `engineering-governance` explicitly forbids a programme
from doing to itself. It is recorded here instead, which is why this file
exists. Opening it means a new authorisation, not a promotion.

Related: the four path-filtered capability gates are **not** required checks.
That is deliberate and recorded in the archived change — a required context that
never reports leaves a pull request permanently unmergeable. It becomes safe to
require them once the aggregating gate job exists, which is the same piece of
work.

### Shipped medallion default versus the recorded rollout state

`docker-compose.extended.yml` and `.env.example` both ship
`SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`, so a fresh stack
performs a full Silver and Gold rebuild every 60 seconds.
`artifacts/b2-rollout/07-rollout-result.md` records that the live runtime
finished its August observation window in the `cutover` state.

Both statements are true and neither is stale. But a reader can reasonably take
the rollout artifact as describing today's default. Whether the shipped default
should advance to `cutover` is a **configuration decision with runtime
consequences**, not a documentation fix, and it was fenced out of the
documentation change rather than settled quietly. The README's *Medallion
rollout modes* section now states which mode ships, so the ambiguity is
documented while the decision waits.

### Evidence citations that name no invocation event

The evidence-shape fitness function requires a `pull_request` citation to record
its base branch and base SHA. It cannot act on a citation that gives a run id
but never says which event produced it.

Closing that would mean requiring every run citation to name its event.
Measured against the archive: **109** blocks cite a run id and **19** name an
event. Rewriting ninety historical citations would be a wholesale edit of the
archive to enforce a property the requirement does not state. The rule catches
what actually went wrong — a `pull_request` receipt offered as adoption evidence
without saying what it merged into — and the residual is recorded rather than
quietly carried.

### Local directories outside the repository

The container folder holds `h1-artifacts`, `ng05-ci-artifact` and `scratch` from
earlier sessions. They are not tracked, not referenced by any evidence, and were
left untouched — they are local working data, and deleting another session's
files is not cleanup.

## Resuming

1. `git fetch origin` and confirm `main` is `770a9018` or later.
2. Read `AGENTS.md` — **Development workflow** first. Branches start from
   current `main`; pull requests target `main`; an existing worktree is not
   evidence of a valid base.
3. Pick work from `openspec/backlog/next-generation/00-INDEX.md`. A `PLANNED`
   row authorises nothing; starting one means opening the change its row names,
   under a fresh operator authorisation.
4. Re-verify external premises before accepting any backlog item's design. The
   items record versions and capabilities as of the date they were written.
