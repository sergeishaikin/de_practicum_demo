## ADDED Requirements

### Requirement: Recorded future work lives in the backlog and authorises nothing

Work that has been specified but not authorised SHALL be recorded under
`openspec/backlog/`, and SHALL NOT be recorded as a change under
`openspec/changes/` until it is authorised.

A backlog item SHALL NOT be cited as authorisation to execute, and SHALL NOT be
cited as evidence of how the repository behaves. Its requirements describe
intended future state; the standing capabilities under `openspec/specs/`
describe the present one.

A backlog index SHALL name, for each item, the OpenSpec change it opens as and
whether it is authorised, so that two people cannot start the same work under
two change names and so that the authorisation state is readable without
opening the item.

#### Scenario: A specified item is picked up

- **WHEN** a backlog item is started
- **THEN** it is opened as the change its backlog row names, with its own
  proposal, scope fence and explicit authorisation
- **AND** the backlog row is not treated as the authorisation

#### Scenario: A backlog requirement is quoted as current behaviour

- **WHEN** a reader finds a `SHALL` statement in a backlog item
- **THEN** it is read as a requirement on unbuilt work
- **AND** it is not reported as a capability the repository has

#### Scenario: An item is small enough to do immediately

- **WHEN** a backlog item's work looks cheap enough to land alongside something
  already authorised
- **THEN** it still requires its own change and its own authorisation, because
  the cost of the work is not what authorisation measures
