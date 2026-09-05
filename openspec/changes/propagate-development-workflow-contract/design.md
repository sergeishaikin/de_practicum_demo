# Design: propagate-development-workflow-contract

## The gap this closes

`standardize-trunk-based-development` treated the integration contract as a
verification problem and solved it as one. Its fitness functions
(`tests/test_development_workflow_contract.py`) check that standing CI does not
name working branches, that capability gates declare `workflow_call` and retain
`workflow_dispatch`, that a gate triggers on edits to itself, and that the
dispatcher requires a full expected SHA. Its Milestone 2 applied `main`
protection, squash-only merging and `delete_branch_on_merge`.

Every one of those acts on or after a merge candidate. None of them acts on the
choice of base, which happens before the first commit and is made from
documents.

```text
                     ┌──────────────────────────────────────┐
   author reads ────►│ AGENTS.md / CLAUDE.md / DEVELOPMENT   │  ← contract absent
                     └───────────────┬──────────────────────┘
                                     │
                            chooses base branch          ← the governed decision
                                     │
                                     ▼
                            first commit … push
                                     │
                     ┌───────────────▼──────────────────────┐
                     │ CI fitness functions, main protection │  ← contract enforced
                     └──────────────────────────────────────┘
```

The enforcement is downstream of the decision it exists to govern. That is why
`feature/ng-0.7-grafana-correlation` could be opened on a legacy baseline four
days after the capability was adopted, without any gate objecting: no gate runs
at the point where the mistake is made, and the documents that do reach that
point said nothing.

## Measured state before the change

Measured on 2026-09-05 against `main` at `978863d`, and against `acbce84`
(`main` before #14) where the change was first drafted. Both give the same
result; none of the three documents changed between them.

| Document | Cites canonical spec | States branch origin | States PR target | Carries falsified claim |
|---|---|---|---|---|
| `AGENTS.md` | no | no | no | — |
| `CLAUDE.md` | no | no | no | — |
| `docs/DEVELOPMENT.md` | no | no | no | yes, two |

The two falsified claims in `docs/DEVELOPMENT.md`:

- "No explicit convention is documented (`CONTRIBUTING.md` and
  `.github/PULL_REQUEST_TEMPLATE.md` do not exist)."
- "No pull-request template or review workflow is defined."

Both were true when written. `standardize-trunk-based-development` made the
first false and the second half-false — there is still no template, but a
review workflow is now specified and enforced by branch protection.

`AGENTS.md`'s **Planning methodology** section named two standing capabilities.
`openspec/specs/` holds seven. The enumeration was not merely incomplete; it
was the sentence a reader consults to learn what governs their work, and
`development-workflow` was the capability missing from it.

## The motivating incident, by immutable identity

Recorded so the requirement is anchored to a fact rather than to a concern.

| | |
|---|---|
| Branch | `feature/ng-0.7-grafana-correlation` |
| Created at | `d031679` — tip of `test/dbt-extensive-testing`, a recorded exception branch |
| First commit | `9882d98` `docs(openspec): design NG-0.7 correlation and SLI layer`, pushed to `origin` |
| `main` at that time | `acbce84`; `d031679` had `main` as neither ancestor nor descendant (7 behind, 11 ahead) |
| Requirement breached | **Implementation branches originate from current `main`** |
| Repaired | rebased `--onto main`, `9882d98` → `cc2c16d`, force-pushed with lease on 2026-09-05 |

The repair is recorded here as context, not as this change's work: it was a Git
operation on another branch and produced no commit on this one. What belongs to
this change is the reason the mistake was available to make.

## Why a spec delta rather than only a test

The fitness function asserts that three documents contain particular content.
Without a requirement behind it, that is an arbitrary rule enforced by a test —
exactly the shape the repository rejects elsewhere, and something a later
author would be right to delete as unmotivated.

The added requirement also states the part a checker cannot: that propagation
belongs to the change that adopts a capability, not to a follow-up. A test can
only observe that a document is currently wrong; the requirement says whose job
it was to be right.

## Why the rules match normalised text

The checker strips markdown emphasis and code spans and flattens whitespace
before matching. Matching raw text would make the gate an assertion about
prose formatting: reflowing a paragraph, or changing `` `main` `` to **main**,
would fail a check about branching policy. The normalised form matches the two
load-bearing phrases — "from the current main" and "target main" — and the
canonical spec path.

This is deliberately weaker than parsing meaning. It catches a document that
never states the rule, and a document that still carries a superseded claim.
It would not catch a document that states the rule and then contradicts it in
the next paragraph. That residual is accepted: the failure mode observed here
was silence and staleness, not contradiction.

## Rejected alternative: add `CONTRIBUTING.md`

A `CONTRIBUTING.md` is the conventional home for this material, and
`docs/DEVELOPMENT.md` named its absence. It is not added, for two reasons. It
would be a fourth place the contract lives, and the propagation requirement
would then have to name it or drift around it. And the audience that caused
this defect — agents reading `AGENTS.md` and `CLAUDE.md` — would not read it.
Adding a document for a human convention while the agent instructions stayed
silent would repeat the mistake in a new file.
