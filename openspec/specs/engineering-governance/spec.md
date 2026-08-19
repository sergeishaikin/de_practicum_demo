# Engineering governance

How work in this repository is planned, authorised and executed after the
2026-08-18 cutover from GSD execution to OpenSpec.

## Purpose

`.planning/` recorded a phase/plan workflow that executed Phases 1–4. That
history stays in the repository as evidence. New work is planned as OpenSpec
changes instead, so that one directory holds both the intent and the record of
what was decided, and so that a planning artifact cannot be created outside
version control.

## Requirements

### Requirement: Outstanding work is planned as an OpenSpec change

New work SHALL be proposed as a change under `openspec/changes/`, not as a new
plan under `.planning/phases/`.

#### Scenario: A defect is found by CI

- **WHEN** a repository gate fails and the cause is not yet understood
- **THEN** a change is created whose intent is to classify the failure
- **AND** runtime behaviour is not modified until the classification is
  supported by evidence

#### Scenario: A migrated obligation is picked up

- **WHEN** work that was an unexecuted `.planning/` plan is started
- **THEN** it is started as the OpenSpec change it was migrated to, and the
  original plan is not executed through GSD phase orchestration

### Requirement: `.planning/` is historical evidence, not a live queue

Completed `.planning/` artifacts SHALL remain tracked and unedited except to
record that execution was frozen. They SHALL NOT be resumed as a work queue.

#### Scenario: An unchecked plan box remains in ROADMAP.md

- **WHEN** a reader finds `- [ ] 04-08-PLAN.md` or a similar unchecked entry
- **THEN** the obligation is read from the migration mapping in
  `.planning/STATE.md`, and the work happens in the mapped OpenSpec change

### Requirement: A change states its scope fence before work starts

A change SHALL state what it is allowed to touch and what it is not, and the
fence SHALL be checkable rather than descriptive.

#### Scenario: A diagnostic change is tempted into a fix

- **WHEN** the likely remedy becomes apparent during diagnosis
- **THEN** the change does not apply it, because a diagnostic change's fence
  forbids changing behaviour before classification
- **AND** the remedy is proposed as its own change

### Requirement: Authorisation is explicit and per change

Execution of a change SHALL require the operator's explicit authorisation, and
an authorisation SHALL NOT extend to the next change.

#### Scenario: A change completes and a successor is obvious

- **WHEN** a change is finished and the next one is already written
- **THEN** work stops until the operator authorises the successor

### Requirement: A contradiction between a plan and the code stops the work

WHEN an artifact's instruction cannot be followed because the code behaves
otherwise, the work SHALL stop and report the contradiction rather than adjust
tests, expected values or prose to make the artifact appear correct.

#### Scenario: An acceptance check cannot be satisfied truthfully

- **WHEN** satisfying a stated acceptance criterion would require writing
  something untrue
- **THEN** the criterion is reported as defective, the accurate form is written,
  and the deviation is recorded in the change

### Requirement: A deferral records what would reopen it and is not a refutation

WHEN a decision defers an item rather than adopting or rejecting it, the record
SHALL state the conditions under which the item is reconsidered, and SHALL NOT
be written in a form that reads as evidence the item is unnecessary.

A deferral is a statement about the evidence available now. Recording it as a
settled conclusion transfers a certainty the evidence never carried to every
later reader, who has no way to tell the two apart from the record alone.

#### Scenario: A gate selects a no-change outcome

- **WHEN** a decision gate resolves to leaving deferred items unopened
- **THEN** the record names each deferred item, the observed evidence, and the
  conditions that would open it
- **AND** it does not state or imply that the item was found unnecessary

#### Scenario: A later reader looks up the closed decision

- **WHEN** the decision is consulted before proposing the deferred work
- **THEN** the record supplies the trigger conditions to test against, rather
  than a conclusion that forecloses the proposal

### Requirement: Recorded future work lives in the backlog and authorises nothing

Work that has been specified but not authorised SHALL be recorded under
`openspec/backlog/`, and SHALL NOT be recorded as a change under
`openspec/changes/` until it is authorised.

A backlog item SHALL NOT be cited as authorisation to execute, and SHALL NOT be
cited as evidence of how the repository behaves. Its requirements describe
intended future state; the standing capabilities under `openspec/specs/`
describe the present one.

A backlog register SHALL name, for each item, the OpenSpec change it opens as and
whether it is authorised, so that two people cannot start the same work under
two change names and so that the authorisation state is readable without
opening the item.

#### Scenario: A specified item is picked up

- **WHEN** a backlog item is started
- **THEN** it is opened as the change its register row names, with its own
  proposal, scope fence and explicit authorisation
- **AND** the register row is not treated as the authorisation

#### Scenario: A backlog requirement is quoted as current behaviour

- **WHEN** a reader finds a `SHALL` statement in a backlog item
- **THEN** it is read as a requirement on unbuilt work
- **AND** it is not reported as a capability the repository has

#### Scenario: An item is small enough to do immediately

- **WHEN** a backlog item's work looks cheap enough to land alongside something
  already authorised
- **THEN** it still requires its own change and its own authorisation, because
  the cost of the work is not what authorisation measures

### Requirement: Backlog ordering is not chained authorisation

Completing a backlog item SHALL NOT authorise any item that depends on it.
Satisfying a dependency makes the dependent item *eligible* for authorisation
and nothing more.

An execution order, a dependency layer, a priority ranking and a recommended
next step are all statements about sequence. None of them is a grant. Work
SHALL stop at the end of each authorised change and wait for a separate
authorisation, including when the next item is unambiguous, already written, and
the only thing that could sensibly come next.

This binds autonomous execution in particular: an agent that has just satisfied
an item's dependencies has thereby produced eligibility, not permission.

#### Scenario: A dependency completes and unblocks exactly one successor

- **WHEN** an authorised change completes and its backlog item was the sole
  blocker of one dependent item
- **THEN** the dependent item becomes eligible for authorisation
- **AND** work stops until the operator authorises it separately

#### Scenario: An agent finishes an item while running unattended

- **WHEN** execution is autonomous and the next item is obvious from the register
- **THEN** the agent reports completion and stops
- **AND** it does not open the successor's change on the strength of the ordering

#### Scenario: A whole layer becomes eligible at once

- **WHEN** completing one item makes several independent items eligible
- **THEN** each of them requires its own separate authorisation
- **AND** authorising one of them does not authorise its layer-mates

### Requirement: Backlog premises are revalidated at promotion

Externally time-sensitive premises recorded in a backlog item — product
versions, compatibility matrices, resource requirements, connector capabilities
and documented product limitations — SHALL be treated as planning assumptions
captured on a date, not as established facts.

WHEN a backlog item is promoted to an authorised change, every such premise
SHALL be re-verified against primary documentation before the design is
accepted. A premise that cannot be re-verified SHALL be recorded as unverified;
it SHALL NOT be carried into the design on the authority of the backlog
document.

A backlog item ages silently: nothing about reading it reveals that the version
matrix it names was superseded, so the obligation to recheck has to sit with the
promotion rather than with the reader's judgement.

#### Scenario: A pinned version line has moved on

- **WHEN** an item names a compatibility set and a newer supported combination
  exists at promotion time
- **THEN** the change re-verifies and records the current set
- **AND** the backlog document is not treated as authority for the stale one

#### Scenario: A gap the item claims has since been closed

- **WHEN** an item's premise is that the repository lacks some capability, and
  that capability has since landed
- **THEN** the change records that the premise no longer holds and the scope is
  re-derived before design is accepted

### Requirement: Backlog contradictions stop implementation

WHEN an authorised change discovers that its backlog item contradicts the
register, or contradicts itself, implementation SHALL stop before state-changing
work. The contradiction SHALL be resolved explicitly — as a bounded backlog
correction, or as an authoritative interpretation recorded in the register —
**before** the change's design is accepted.

An implementing change SHALL NOT decide, in its own design, which line of the
backlog was the correct one. A governed specification that disagrees with itself
is a defect in the specification; letting the implementation pick a reading
retroactively rewrites what the backlog meant, and leaves no record that the
question was ever open.

A provisional reading recorded in the register to keep the structure valid is
not a resolution, and SHALL be labelled as interim.

#### Scenario: An item's dependency list contradicts the register

- **WHEN** an authorised change finds its item declares a dependency the
  register does not, or the reverse
- **THEN** work stops before any state-changing step
- **AND** the contradiction is resolved as a backlog correction or a recorded
  authoritative interpretation before the design is accepted

#### Scenario: An item contradicts itself

- **WHEN** an item names something as a dependency in one section and calls it
  a recommendation in another
- **THEN** the register may carry the stricter reading as an interim
  interpretation so the structure stays checkable
- **AND** that interim reading is not treated as the decision

#### Scenario: The contradiction is discovered mid-implementation

- **WHEN** the disagreement surfaces after the change has begun
- **THEN** the change stops rather than proceeding on whichever reading suits
  the work already done

### Requirement: A backlog register is structurally checkable

A backlog register SHALL be machine-checkable rather than only drawn, and the
check SHALL be executable from the repository.

At minimum the check SHALL assert that item ids are unique and well-formed, that
pre-assigned change ids are unique across the backlog, that every declared
dependency resolves to a known item, that the dependency graph is acyclic, that
row order is a valid execution order, that every authorisation cell is either
`no` or a date, and that every referenced item file exists and still declares
itself unauthorised future work.

Any diagram or layering published alongside a register SHALL be derivable from
that register. A drawing that disagrees with the table is a defect in the
drawing.

#### Scenario: Two items are given the same change id

- **WHEN** a register assigns one change id to two items
- **THEN** the structural check fails and names both items

#### Scenario: A dependency edit introduces a cycle

- **WHEN** a dependency is added that makes the graph cyclic, or that references
  an item appearing later in the register
- **THEN** the structural check fails and names the offending path

#### Scenario: An authorisation cell is edited by hand

- **WHEN** an item's authorisation cell is changed to anything other than `no`
  or an ISO date
- **THEN** the structural check fails rather than accepting free text

### Requirement: A hard dependency is a technical prerequisite

A dependency recorded in a backlog register SHALL be a technical prerequisite:
the dependent item cannot be designed, implemented, or have its acceptance
evidence produced until the dependency exists.

The following SHALL NOT be recorded as dependencies:

- a preferred or recommended order;
- a rule the other item would impose *if* it existed;
- a layering convention inherited from how the items were first written down;
- a relationship the item's own body describes as "recommended", "preferred" or
  "where available".

Each of those is real and SHALL be recorded, but as a stated preference rather
than in the dependency column, because only the column gates work.

Over-gating is not a safe default. A false dependency blocks work that nothing
blocks, and it contradicts any ordering that reflects the real constraint —
which is how a register and a recommended ordering can each be internally
consistent and still disagree.

#### Scenario: An item lists a prerequisite it never consumes

- **WHEN** an item declares a dependency that nothing in its requirements,
  acceptance evidence or design would use
- **THEN** the dependency is removed from the register and the item body
- **AND** the reason it was listed is recorded, so the removal is not mistaken
  for an oversight

#### Scenario: Trimming one item's dependencies un-gates another

- **WHEN** a dependent item was reaching a prerequisite only transitively,
  through an edge being removed
- **THEN** that prerequisite is recorded explicitly on the dependent item before
  the edge is removed
- **AND** the dependency model is verified to be unchanged for every item other
  than the ones deliberately corrected

### Requirement: A published ordering respects the dependency graph

Any document that publishes an execution, priority or scheduling order for
backlog items — including an ADR — SHALL NOT place an item before one of its
hard dependencies, and the relationship SHALL be machine-checked rather than
maintained by inspection.

The register names the ordering document. The ordering document marks each
execution slot unambiguously, so that commentary naming an item is not mistaken
for scheduling it. A published ordering SHALL cover every item in the register
exactly once.

An ordering and a register can each be internally valid while contradicting each
other, and neither document's own checks can see it. That contradiction is
therefore a check across the two, not within either.

#### Scenario: An ordering is published that inverts a dependency

- **WHEN** a scheduling document recommends an item ahead of a hard dependency
- **THEN** validation fails, naming the item, the dependency and both positions
- **AND** the disagreement is resolved before either document is relied on

#### Scenario: A dependency is corrected and the ordering still holds

- **WHEN** removing a false dependency makes an existing recommended order
  consistent
- **THEN** the ordering is not rewritten merely because it was re-examined
- **AND** the amendment records that the reasoning is unchanged and only the
  derived facts were restated

#### Scenario: An ordering document explains itself

- **WHEN** the document names an item in commentary — a paper gate, an
  annotation, a rejected option
- **THEN** that mention is not treated as an execution slot
