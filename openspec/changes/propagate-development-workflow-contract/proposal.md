# Proposal: propagate-development-workflow-contract

## Problem

`standardize-trunk-based-development` promoted `development-workflow` to a
standing capability and brought CI and repository settings into conformance
with it. It did not touch the documents an author reads before the first
commit, and nothing in the capability required it to.

The result is a contract that is enforced but not discoverable:

- `AGENTS.md` — the authoritative repository instruction file — named
  `engineering-governance` and `verification-contract` as the standing
  capabilities and stopped there. It described authorisation and verification
  as the whole of the process contract, and said nothing about where a branch
  originates or what a pull request targets.
- `CLAUDE.md` deferred verification to `AGENTS.md` but stated no branch, base
  or integration rule. Its **Repository location** section instructed the
  reader to "run all commands from the inner directory" — a worktree that is
  checked out on `test/dbt-extensive-testing`, one of the capability's two
  recorded exception branches.
- `docs/DEVELOPMENT.md` still stated that "No explicit convention is
  documented (`CONTRIBUTING.md` and `.github/PULL_REQUEST_TEMPLATE.md` do not
  exist)" and recommended a generic `feature/<short-name>` topic-branch flow,
  with a PR process beginning "Fork the repository and create a topic branch."

An agent or contributor could therefore obey OpenSpec authorisation and the
verification contract in full and still branch new work off a legacy
integration baseline. That is not hypothetical. `feature/ng-0.7-grafana-
correlation` was created at `d031679` — the tip of `test/dbt-extensive-testing`
— rather than from `main`, and its design commit `9882d98` was pushed from that
base. The branch violated **Implementation branches originate from current
`main`** on its first commit, four days after the requirement was adopted.

The enforcement built by the previous change cannot reach this. CI fitness
functions check workflow topology; `main` protection checks the merge. Both act
after the base has already been chosen. The base is chosen from the documents,
and the documents did not carry the rule.

## Proposed bounded change

Require the integration contract to be stated where authors read it, and bring
the three documents into conformance.

Add two requirements to `development-workflow`. The first: the contract SHALL be
stated in the repository's contributor- and agent-facing instruction documents,
which SHALL cite the canonical spec and SHALL NOT carry claims the contract has
falsified. Extend `tests/test_development_workflow_contract.py` — which already
holds this capability's fitness functions — to check propagation as well as CI
topology.

The second closes an adjacent gap found while carrying forward the stale
`governance/branch-closure-rule` branch: cleanup SHALL be part of Definition of
Done. The existing **Integrated branches are deleted automatically** requirement
says branches are deleted but not when the obligation falls due, and says
nothing about the worktrees that accumulate alongside them. It also lacked the
safety rule that a dirty worktree is never force-removed, and the preference for
an immutable tag over a branch that reads as active.

## Non-goals

- No change to any existing `development-workflow` requirement. This change
  adds one and restates none.
- No new document. `CONTRIBUTING.md` and a pull-request template remain absent;
  the contract lives in the three documents that already exist and are already
  read.
- No new test file, framework or runner. The rules join the capability's
  existing fitness-function module.
- No duplication of the spec into `CLAUDE.md`. `CLAUDE.md` carries the
  operational preflight and points at the canonical text; restating fifteen
  requirements there would recreate the drift this change exists to close.

## Scope fence

- This change SHALL NOT modify `README.md`. Its architecture diagram, medallion
  description and resource-profile table have separately identified defects;
  they are not integration-contract defects and are not absorbed here.
- This change SHALL NOT delete `feature/ng-0.6-loki` or
  `test/dbt-extensive-testing`, and SHALL NOT edit the capability's **Recorded
  exceptions** table. NG-0.6 adoption integrated as #14 on 2026-09-04, which
  may now satisfy both end conditions, but confirming that and re-anchoring the
  NG-0.6 evidence is its own change.
- This change SHALL NOT add the deferred evidence-shape fitness function
  (evidence citing a `pull_request` run records its base branch and base SHA).
  That task is recorded in the archived `standardize-trunk-based-development`
  change and was blocked on NG-0.6; whether NG-0.6's integration unblocked it
  is a question for the change that owns it.
- This change SHALL NOT alter runtime, Compose, dbt, Airflow, observability or
  CI configuration, and SHALL NOT change what any acceptance gate asserts.
