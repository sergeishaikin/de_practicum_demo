## ADDED Requirements

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
