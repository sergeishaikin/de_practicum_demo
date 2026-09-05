# Development workflow

## ADDED Requirements

### Requirement: The integration contract is stated where authors read it

The repository's contributor- and agent-facing instruction documents SHALL
state this capability's branch-origin and pull-request-target rules and SHALL
cite `openspec/specs/development-workflow/spec.md` as the canonical text. They
SHALL NOT carry claims that this capability has falsified, including that no
branch or pull-request convention is documented.

A document that instructs a reader where to work SHALL NOT direct them to a
checkout without qualifying which branch it is on, because a repository held as
several worktrees can present a legacy branch as the default working directory.

This requirement exists because enforcement cannot reach the decision it needs
to govern. Standing CI checks workflow topology and `main` protection checks
the merge; both act after a base has been chosen. The base is chosen before the
first commit, from the documents alone. A contract that is enforced but not
stated is one an author can violate while following every instruction they were
given.

Restating the full contract in each document is not required and is not
wanted — a second normative copy drifts. What each document SHALL carry is the
rule that decides the base, and a pointer to the canonical text.

#### Scenario: A capability is adopted into `openspec/specs/`

- **WHEN** a standing capability governs how contributors or agents work
- **THEN** the instruction documents are updated in the same change that adopts
  it
- **AND** adoption is not complete while a document still describes the
  superseded behaviour

#### Scenario: A document predates the contract

- **WHEN** an instruction document states that no convention exists, or
  describes a workflow the capability has replaced
- **THEN** the statement is a defect in the capability's propagation, not
  merely stale prose, and it is corrected rather than annotated

#### Scenario: An agent looks for the branching rule

- **WHEN** an agent consults the repository's instruction files before starting
  governed work
- **THEN** it finds where branches originate and what pull requests target
  without reading `openspec/specs/`

#### Scenario: The repository is checked out as several worktrees

- **WHEN** a document names a directory to run commands from
- **THEN** it records that the directory's branch must be confirmed, and that
  an existing worktree is not evidence of a valid base for new work

### Requirement: Closure includes branch and worktree cleanup

Cleanup SHALL be part of a change's Definition of Done. A change SHALL NOT be
treated as closed because implementation, verification, adoption or integration
passed; closure additionally requires that the work's branches and dedicated
worktree are removed and that the cleanup status is stated in the handoff.

A dirty worktree SHALL NOT be removed or force-cleaned. Every uncommitted change
SHALL be inspected and classified first, then committed, moved, preserved or
explicitly discarded. Unrelated dirty worktrees SHALL be left untouched.

Where a long-lived historical pointer is genuinely needed, an immutable tag
SHALL be preferred over a retained branch, because a branch reads as active work
and a tag does not.

The existing deletion requirement says integrated branches are deleted; it does
not say when that obligation falls due, and it does not mention the working
copies that accumulate alongside the branches. Deferred cleanup is how a
repository acquires branch topology that later readers mistake for state — the
condition that produced this capability's two recorded exceptions.

#### Scenario: The next item is ready before cleanup is done

- **WHEN** a change has integrated and the successor is authorised
- **THEN** the completed change's branches and worktree are removed first
- **AND** starting the successor before cleanup requires a recorded exception

#### Scenario: A worktree for completed work has uncommitted changes

- **WHEN** cleanup reaches a worktree that is not clean
- **THEN** each uncommitted change is classified and preserved or explicitly
  discarded before the worktree is removed
- **AND** the worktree is never force-removed to make cleanup proceed

#### Scenario: Evidence needs a durable pointer after cleanup

- **WHEN** a commit must stay findable after its branch is deleted
- **THEN** it is anchored by SHA, run id and pull request number, and tagged if
  a named pointer is wanted
- **AND** the branch is not retained to serve as the pointer

#### Scenario: A change reports completion

- **WHEN** a change is handed off as done
- **THEN** the report states the branch and worktree cleanup status, so an
  unfinished closure is visible rather than silent
