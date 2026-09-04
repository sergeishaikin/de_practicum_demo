# Development workflow

## ADDED Requirements

### Requirement: `main` is the sole permanent integration branch

`main` SHALL be the only permanent development line. The repository SHALL NOT
maintain permanent `develop`, `integration/*`, `test/*`, `staging/*` or
`release/*` branches as workflow infrastructure.

A branch whose name begins with one of those words is permitted only where it
carries one bounded change and is deleted on integration. What is prohibited is
the permanent lane, not the vocabulary.

#### Scenario: A second long-lived line is proposed

- **WHEN** work is proposed on a standing branch that accumulates changes
  before they reach `main`
- **THEN** the proposal is rejected and the work is decomposed into changes
  that integrate into `main` directly

#### Scenario: A branch outlives its change

- **WHEN** a branch named for a phase, milestone or programme is still
  receiving commits after its change has integrated
- **THEN** it is treated as a permanent lane regardless of its name

### Requirement: Implementation branches originate from current `main`

WHEN an OpenSpec change is authorised, its implementation branch SHALL start
from the current `main`, and its pull request SHALL target `main`.

A branch SHALL NOT be created from another unmerged working branch, and a pull
request SHALL NOT target a branch other than `main` except where the base is
itself an unmerged bounded change that the head genuinely extends.

#### Scenario: Work depends on another change in flight

- **WHEN** new work needs something from a change that has not yet integrated
- **THEN** the dependency is integrated into `main` first, or the new work is
  scoped to what `main` already provides
- **AND** a branch-of-branch chain is not created to carry the dependency

#### Scenario: A pull request targets a legacy branch

- **WHEN** a pull request's base is a branch that is behind `main`
- **THEN** the pull request does not describe a real integration and is not
  opened

### Requirement: One branch carries one bounded change

A governed implementation branch SHALL correspond to one authorised OpenSpec
change or one independently releasable fix, and SHALL NOT accumulate unrelated
work.

The unit is conceptual, not a line count. A branch has breached this
requirement when it can no longer be described without a list — when reviewing
it means reviewing several unrelated decisions that could each have been
declined separately.

#### Scenario: An adjacent improvement is discovered mid-branch

- **WHEN** work outside the change's scope fence would plainly improve the
  repository
- **THEN** it is recorded as a follow-up and left for its own change

#### Scenario: A branch becomes a programme container

- **WHEN** a branch that began as one change has taken on integration,
  observability and governance work that were never in its fence
- **THEN** the branch has become an alternate baseline and the remaining work
  is re-derived onto focused branches from `main`

### Requirement: Divergence from `main` stays small

A working branch SHALL be integrated or replaced before it becomes an
alternate long-lived baseline.

The measurable policy is: integrate within three calendar days; beyond three
days is a warning; beyond seven days requires a recorded rationale in the
change. Elapsed time SHALL NOT be enforced as an automatic failure, because
wall-clock time is a weak proxy — a weekend does not make a healthy pull
request invalid. The invariant is small divergence, and elapsed time is only
its most visible symptom.

#### Scenario: A branch passes the warning threshold while healthy

- **WHEN** a branch is older than three days but small and current with `main`
- **THEN** the age is recorded and the work continues

#### Scenario: A branch has diverged substantially

- **WHEN** a branch has accumulated work that no longer reviews as one change
- **THEN** it is decomposed, regardless of its age

### Requirement: No environment branches

Deployment state SHALL NOT be represented by a branch. The repository SHALL
NOT operate `dev`, `test`, `staging` or `prod` branches that track
environments.

Promotion SHALL move one immutable artifact built from one commit SHA through
environments. The same Docker images, Compose configuration, dbt and runtime
code, Airflow image and verification artifacts that were verified are the ones
promoted; environments differ in configuration and promotion state, never in
source lineage.

#### Scenario: A hotfix is needed in a promoted environment

- **WHEN** a defect is found in a promoted artifact
- **THEN** the fix branches from `main`, integrates into `main`, and a new
  artifact is built and promoted
- **AND** the fix is not applied to an environment branch and back-merged

#### Scenario: Two environments disagree

- **WHEN** environments behave differently
- **THEN** the difference is explained by configuration or promotion state, and
  the deployed SHA of each is recoverable

### Requirement: A pull request means proposed integration

A pull request SHALL mean that its head is proposed for integration into its
base. A pull request SHALL NOT be opened solely to obtain a CI execution
context.

Verification SHALL be invocable by the trigger that matches its purpose:

- `pull_request` — verify a proposed integration
- `workflow_dispatch` — explicit verification of an exact SHA
- `workflow_call` — composition and reuse by another workflow
- `push` to `main` — verify the integrated result
- `schedule` — periodic regression

#### Scenario: An exact-SHA receipt is needed with nothing to integrate

- **WHEN** evidence is required for a commit that is not being proposed for
  integration
- **THEN** the verification is invoked by `workflow_dispatch` on that SHA
- **AND** a pull request is not opened to trigger it

#### Scenario: A validation-only pull request is opened

- **WHEN** a pull request is opened with no intent to merge it
- **THEN** the workflow is defective, not the author's technique, and the
  missing invocation path is added

### Requirement: An adoption receipt proves the candidate against its real integration base

A receipt cited as evidence that a change is ready to integrate SHALL have been
produced against the branch into which the change will actually integrate. For
normal development that branch is `main`.

A receipt produced against a different historical or integration branch SHALL
NOT be cited as evidence that the integration candidate passed, however green
it is. A `pull_request` run verifies the merge of head into **base**; when the
base is not the integration target, the run is evidence about a merge that will
never happen.

Evidence citing a `pull_request` run SHALL record the base branch and its SHA
alongside the head SHA, so that a reader can tell what was actually merged
without reconstructing the pull request.

#### Scenario: A green run was produced against a stale base

- **WHEN** an adoption or closure receipt cites a `pull_request` run whose base
  was behind `main`
- **THEN** the receipt does not support adoption and the verification is re-run
  against the real integration candidate

#### Scenario: A receipt records only the head SHA

- **WHEN** evidence names a head SHA and a run id but not the base
- **THEN** the base cannot be assumed to be `main` and the receipt is
  incomplete

### Requirement: Standing CI definitions do not name working branches

A standing capability workflow SHALL NOT encode the name of a working branch in
its triggers or logic. Capability verification SHALL be selected by what
changed and by explicit invocation, never by which branch the work happens to
be on.

`main` may be named, because it is permanent by the first requirement.

This rule exists because a branch name in a workflow outlives the branch: it
makes deleting an integrated branch a breaking change to CI, and it makes a
gate's coverage depend on a naming accident.

#### Scenario: A capability workflow is pinned to a feature branch

- **WHEN** a workflow triggers on `push` to a named working branch
- **THEN** the fitness function fails and names the workflow and the branch

#### Scenario: An integrated branch is deleted

- **WHEN** a branch is deleted after integration
- **THEN** no workflow's trigger or logic is invalidated

### Requirement: Capability verification is reusable and separately invocable

Each standing acceptance capability SHALL exist as one definition that can be
composed, and SHALL be invocable without opening a pull request.

A capability workflow SHALL declare `workflow_call` so orchestrating workflows
reuse it rather than restating its steps, and SHALL retain `workflow_dispatch`
as the exact-SHA escape hatch. Duplicating a gate's command sequence into a
second workflow SHALL NOT be used in place of composition, because two copies
of a gate are two gates that can disagree.

#### Scenario: The same acceptance is needed in three contexts

- **WHEN** a capability must be verified in a pull request, on `main`, and on
  demand for an exact SHA
- **THEN** one callable definition is invoked from each context

#### Scenario: A gate's assertions are edited

- **WHEN** a capability's checks change
- **THEN** every context that runs that capability reflects the change, because
  there is only one definition to edit

### Requirement: `main` is protected

`main` SHALL reject direct pushes, force pushes and deletion, and SHALL require
a pull request with its required status checks passing and its review
conversations resolved before merge.

Protection is part of the verification boundary, not a preference. A gate that
can be bypassed by pushing directly is not a gate, and an evidence-based
acceptance model that does not enforce its own integration point transfers a
certainty its enforcement never carried.

A change to a required gate SHALL NOT be able to bypass that gate.

#### Scenario: A change is pushed directly to `main`

- **WHEN** a commit is pushed to `main` outside a pull request
- **THEN** the push is rejected

#### Scenario: A required check fails

- **WHEN** a required status check fails on the merge candidate
- **THEN** the merge is blocked and the failure is resolved rather than
  reinterpreted, retried into success, or excluded

### Requirement: Normal integration produces one durable logical change on `main`

Integrating a pull request SHALL add one durable logical change to `main`,
carrying the change's identity rather than its intermediate corrections.

The requirement is on the resulting history, not on a hosting provider's
button. On GitHub today this is squash merge, and merge-commit and rebase
merging are disabled for ordinary pull requests. An exception is permitted
where a pull request deliberately carries several independently revertible
stages, and the exception is recorded in the change.

#### Scenario: A branch carries development noise

- **WHEN** a branch contains fixups, evidence commits and CI corrections
- **THEN** `main` records the change, not the corrections

#### Scenario: Stages must remain independently revertible

- **WHEN** a pull request's commits are separately meaningful and revertible
- **THEN** preserving them is permitted and the reason is recorded

### Requirement: Integrated branches are deleted automatically

A branch SHALL be deleted on integration, and the repository SHALL be
configured to do so automatically. A branch retained deliberately SHALL have a
recorded reason.

Branch count SHALL reflect work in progress. History is preserved by commits,
pull requests, tags, CI runs and the OpenSpec archive; a branch left behind
preserves nothing and is later mistaken for state.

#### Scenario: A branch is fully subsumed by `main`

- **WHEN** a branch is `0` commits ahead of `main`
- **THEN** it carries nothing unique and is deleted

#### Scenario: A branch is kept after integration

- **WHEN** a branch is retained deliberately
- **THEN** the reason is recorded, so the branch is not later read as
  unfinished work

### Requirement: A merged head is closed to further governed work

WHEN a branch has been integrated into `main`, further governed work SHALL NOT
be committed to it. Successor work — including adoption, archival and closure
of the same change — SHALL branch from the current `main`.

A merged branch that keeps receiving commits becomes ambiguous: it names both
what was released and what has happened since, and no reader can tell which
state a reference to it means. The repeated application and reversion of a
governance decision on such a branch is the failure mode this requirement
exists to prevent — it leaves permanent history noise while the decision itself
remains unmade.

#### Scenario: A change needs governance closure after its code merged

- **WHEN** implementation has integrated and only adoption or archival remains
- **THEN** the closure branches from the current `main` as its own change
- **AND** it is not committed to the branch that was already merged

#### Scenario: A merged branch is reused as a workspace

- **WHEN** a decision is staged and unstaged on a branch that already
  integrated
- **THEN** the branch no longer identifies a released state and the work is
  re-derived from `main`

### Requirement: Evidence refers to immutable identity

Acceptance evidence SHALL identify what was verified by commit SHA, workflow
run id, artifact digest, pull request number and archived OpenSpec change.

Evidence SHALL NOT depend on a branch continuing to exist or continuing to
point at the same commit. A branch name is a moving reference; once integrated
branches are deleted automatically, a claim anchored to one is unrecoverable.

Branch deletion is a consequence of successful integration, never a cause of
evidence loss. Before any branch is deleted, every claim that depended on it
SHALL already be anchored to immutable identity — commit SHA, workflow run id,
artifact digest, pull request number, archived OpenSpec change. Cleanup that
would make a recorded claim unverifiable is not cleanup; it is the destruction
of the record, and the correct response is to anchor the claim first, not to
retain the branch indefinitely.

#### Scenario: Cleanup would orphan a recorded claim

- **WHEN** a branch proposed for deletion is named by evidence that has no
  immutable anchor
- **THEN** the claim is re-anchored to SHA, run id and pull request number
  before the branch is deleted
- **AND** the branch is not retained as the anchor

#### Scenario: A branch named in evidence has been deleted

- **WHEN** a reader follows a receipt after the branch was deleted
- **THEN** the SHA, run id and artifacts still identify exactly what was
  verified

#### Scenario: A branch named in evidence has moved

- **WHEN** a branch cited in a receipt has advanced since the receipt was
  written
- **THEN** the receipt still refers to the SHA it verified, not to the branch's
  current tip

### Requirement: Upstream is provenance, not an integration source

`sergeishaikin/de_practicum_demo` is a fork of `dim4eg91/de_practicum_demo`.
As of 2026-09-04 `origin/main` is 389 commits ahead of `upstream/main` and 0
behind. Upstream SHALL be treated as provenance: there is no routine sync, no
automatic merge from `upstream/main`, and no branching structure designed
around upstream contribution.

This is a deferral, not a finding that upstream integration is unnecessary. It
is reconsidered if upstream becomes active again, or if this project intends to
contribute changes upstream; either condition requires a separate change
defining an upstream sync and contribution workflow.

#### Scenario: Upstream publishes new commits

- **WHEN** `upstream/main` advances
- **THEN** the trigger condition is met and an upstream-sync workflow is
  proposed as its own change
- **AND** upstream commits are not merged into `main` under this capability

#### Scenario: A reader consults the fork policy

- **WHEN** the fork relationship is questioned
- **THEN** the record supplies the conditions that reopen it, rather than a
  conclusion that forecloses the question
