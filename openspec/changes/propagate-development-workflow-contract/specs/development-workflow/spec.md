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
