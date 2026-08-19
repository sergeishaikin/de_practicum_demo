## ADDED Requirements

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
