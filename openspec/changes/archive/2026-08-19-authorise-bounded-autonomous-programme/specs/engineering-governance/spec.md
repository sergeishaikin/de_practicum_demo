## MODIFIED Requirements

### Requirement: Authorisation is explicit and per change

Execution of a change SHALL require the operator's explicit authorisation, and
an authorisation SHALL NOT extend to the next change.

The single exception is a **bounded programme authorisation**, defined below. It
is explicit, it is recorded, and it names in advance the closed set of work it
covers. Nothing else extends an authorisation, and a programme authorisation
SHALL NOT be inferred from enthusiasm, momentum, obviousness, or a sequence of
successful changes.

#### Scenario: A change completes and a successor is obvious

- **WHEN** a change is finished and the next one is already written
- **THEN** work stops until the operator authorises the successor, unless a
  recorded bounded programme authorisation already covers that successor

#### Scenario: A programme authorisation is claimed but not recorded

- **WHEN** work continues across changes on the strength of an authorisation
  that is not written down in this repository
- **THEN** the work is unauthorised regardless of what was said

### Requirement: Backlog ordering is not chained authorisation

Completing a backlog item SHALL NOT authorise any item that depends on it.
Satisfying a dependency makes the dependent item *eligible* for authorisation
and nothing more.

An execution order, a dependency layer, a priority ranking and a recommended
next step are all statements about sequence. None of them is a grant. Work
SHALL stop at the end of each authorised change and wait for a separate
authorisation, including when the next item is unambiguous, already written, and
the only thing that could sensibly come next — unless a recorded bounded
programme authorisation already covers the successor, in which case the
programme's own membership rules decide, and eligibility still does not.

This binds autonomous execution in particular: an agent that has just satisfied
an item's dependencies has thereby produced eligibility, not permission.

#### Scenario: A dependency completes and unblocks exactly one successor

- **WHEN** an authorised change completes and its backlog item was the sole
  blocker of one dependent item
- **THEN** the dependent item becomes eligible for authorisation
- **AND** work stops until the operator authorises it separately, or until a
  recorded programme authorisation is shown to cover it

#### Scenario: An agent finishes an item while running unattended

- **WHEN** execution is autonomous and the next item is obvious from the register
- **THEN** the agent continues only if a recorded programme authorisation covers
  that item; otherwise it reports completion and stops
- **AND** it does not open the successor's change on the strength of the ordering

#### Scenario: A whole layer becomes eligible at once

- **WHEN** completing one item makes several independent items eligible
- **THEN** each of them requires authorisation, whether individually or through a
  recorded programme
- **AND** authorising one of them does not authorise its layer-mates

## ADDED Requirements

### Requirement: A bounded programme authorisation covers a closed, pre-named set

The operator MAY authorise a programme spanning several changes. Such an
authorisation SHALL be recorded in this repository before the programme's first
change is archived, and SHALL state:

- the closed set of work it covers, by a rule that can be evaluated against the
  canonical sources rather than by judgement;
- what it explicitly does not cover;
- the conditions that end it.

A programme authorisation SHALL NOT be open-ended. "Whatever comes next" is not a
membership rule.

Each item in the programme SHALL still be executed as its own OpenSpec change,
with its own scope fence, its own verification and its own archive. A programme
authorises the *sequence*; it does not merge the work, and it does not relax any
gate that would otherwise apply.

Before each item, the executing agent SHALL re-read the canonical sources rather
than follow a plan made earlier in the programme. A programme that ran for
several changes has, by construction, changed the repository those changes were
planned against.

#### Scenario: An item sits outside the programme's membership rule

- **WHEN** the next eligible item is not covered by the recorded rule
- **THEN** the programme does not extend to it, and work stops for a separate
  authorisation

#### Scenario: The backlog changes mid-programme

- **WHEN** an earlier change in the programme alters dependencies, priorities or
  the register
- **THEN** the next item is selected from the current canonical sources
- **AND** a selection made before that change is discarded rather than honoured

#### Scenario: A gate fails during a programme

- **WHEN** lint, typing, tests or CI fail because of the change in progress
- **THEN** the failure is resolved within that change's scope and the programme
  continues
- **AND** the gate is not weakened, retried into success, or excluded to keep the
  programme moving

### Requirement: A programme authorisation never covers its own extension

A programme SHALL NOT authorise changes to the rules that bound it. Widening a
programme's membership, relaxing a gate it must pass, weakening a fail-closed
contract, or amending this capability are outside every programme authorisation
and require the operator's separate decision.

An agent executing a programme SHALL NOT resolve a blocking contradiction by
editing the governance that blocks it.

#### Scenario: Governance blocks the programme's next step

- **WHEN** continuing would require changing a standing requirement
- **THEN** the programme stops and reports the contradiction
- **AND** the requirement is not amended inside the programme to unblock it

#### Scenario: An adjacent improvement is attractive

- **WHEN** work outside the programme's set would plainly improve the repository
- **THEN** it is recorded as a follow-up and left untouched
