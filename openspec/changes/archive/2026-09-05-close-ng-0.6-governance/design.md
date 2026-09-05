# Design: close-ng-0.6-governance

## How base identity was recovered

Not inferred. GitHub's workflow-run API returns an empty `pull_requests` array
for every run cited here, so the base was taken from the pull request each run
belonged to, matched by head branch and head SHA:

| Run(s) | Head | PR | Base |
| --- | --- | --- | --- |
| `32193696670` | `test/dbt-extensive-testing@399957b0` | #1 | `main@33316ece` |
| `32295338891` | `test/dbt-extensive-testing@b14dcc24` | #1 | `main@33316ece` |
| `33888257726`, `33888257735` | `feature/ng-0.6-loki@2e1005b5` | #5 | `test/dbt-extensive-testing@9d62da49` |
| `33890376252` | `feature/ng-0.6-loki@de68270a` | #6 | `test/dbt-extensive-testing@9d62da49` |
| `33904147775` | `feature/ng-0.6-loki@9eb43562` | #9 | `test/dbt-extensive-testing@9d62da49` |
| `33901538965`, `33901538879` | `feat/standardize-trunk-based-development@03416c6c` | #8 | `main@e697f305` |

**The one caveat, stated rather than buried.** GitHub records one `baseRefOid`
per pull request, not one per run. For a short-lived pull request these are the
same thing. For a long-lived one — #1 in particular — the recorded base SHA
identifies the base the pull request was associated with, not necessarily the
base tip at the moment an individual run executed. The base *branch* is exact
in every case; the base *SHA* is exact for #5–#9 and for #8, and is the pull
request's recorded base for #1. That is the strongest claim the surviving data
supports, and it is weaker than pretending to a per-run base SHA that GitHub
never stored.

The independently corroborating fact is that `9d62da49` for #5–#9 matches what
NG-0.6's own evidence already said in prose: base `test/dbt-extensive-testing`,
"fifteen commits behind `main`".

## The checker's unit is the section, not the line

The requirement is that a reader can tell what was merged. This repository
satisfies that by stating the base once under a heading and then tabulating the
runs beneath it — `standardize-trunk-based-development` does exactly that, with
`Base branch` and `Base SHA` rows above its run table.

A line-scoped or row-scoped rule would have declared that conforming file
non-conforming and forced the base to be repeated into every row. So the
section is the unit, and a section satisfies the rule through either form:

- inline, `base main@978863de`; or
- tabulated, a `Base branch` row and a `Base SHA` row.

## Why the trigger is an event label, not the token

A first draft flagged this paragraph:

> `ci-h1-clean.yml` does not list its own path in the `pull_request` paths
> filter … The `workflow_dispatch` run started on that mistaken assumption
> (`32193725758`) was cancelled as a duplicate full rebuild.

It contains `pull_request` and a run id, and cites no `pull_request` run at
all — it explains path-filter semantics and then names a `workflow_dispatch`
run. Demanding a base SHA there would have had exactly one remedy available:
writing a false one. So the detector requires `pull_request` in an event-label
position — `event: pull_request`, `pull_request events`, `pull_request run` —
or a table row that pairs the token with a run id. A regression test pins that
paragraph as a non-citation.

## The residual, and why it is accepted rather than closed

A citation that gives a run id but never names its invocation event escapes the
rule. Closing that hole means requiring every run citation to name its event.
Measured against the corpus: **109** blocks cite a run id and **19** name an
event. Rewriting ninety historical citations would be a wholesale edit of the
archive, and it would enforce a property the requirement does not state.

The rule as written catches what actually went wrong: a `pull_request` receipt
offered as adoption evidence without saying what it merged into. The residual
is recorded here so a later reader finds a measured decision rather than an
oversight.

## Why archived evidence was edited at all

An archive that cannot be corrected accumulates claims nobody may fix. What is
frozen is the *conclusion* a receipt reached; the base branch and base SHA are
facts about a run that were always true and were simply not written down.
Nothing in this change alters a run id, a conclusion, or what any receipt is
offered as evidence for. The Class 1 receipts in NG-0.6's evidence remain
explicitly not adoption evidence, and now say why with the base in hand.
