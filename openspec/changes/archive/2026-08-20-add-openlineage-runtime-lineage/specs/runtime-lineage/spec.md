## ADDED Requirements

### Requirement: A lineage edge is claimed only by the boundary that performed it

A lineage event SHALL name as its inputs and outputs only the datasets the
emitting boundary actually read and wrote during that execution. A relationship
that is known to hold but was not performed by the emitting boundary SHALL NOT
be emitted as an edge of that boundary's job.

An edge that cannot be emitted SHALL be recorded as a named gap with its reason,
in the same place the graph is documented. An unclaimed edge is a smaller defect
than a misattributed one, because a labelled hole can be closed while a false
edge propagates into every consumer of the graph.

#### Scenario: A boundary can derive an edge it did not perform

- **WHEN** a boundary holds data from which an upstream relationship could be
  reconstructed, but did not itself read that upstream dataset
- **THEN** it SHALL NOT emit that relationship as its own input edge
- **AND** the relationship SHALL be recorded as a documented gap instead

#### Scenario: An integration is unavailable for the deployed runtime version

- **WHEN** the vendor integration that would emit an edge publishes no build for
  the engine version this repository runs
- **THEN** the integration SHALL remain disabled
- **AND** the blocker SHALL be recorded with the primary-source evidence that
  establishes it, rather than the engine being changed to suit the integration

### Requirement: One edge has exactly one owner

Each output dataset SHALL have exactly one emitting boundary. A second boundary
claiming an output dataset already claimed by another SHALL fail at registration
rather than producing a duplicate or contradictory edge.

#### Scenario: Two producers claim one output dataset

- **WHEN** a boundary registers an output dataset that another boundary has
  already registered
- **THEN** registration SHALL raise
- **AND** the error SHALL name both claimants

### Requirement: Lineage failure is observable and never corrupting

Lineage emission SHALL NOT alter, delay past its own bounded limits, or fail the
data path. A transport error, an unreachable backend or a fault inside an
emitter SHALL be logged and counted, and processing SHALL continue.

A lineage failure that is invisible is not acceptable merely because it is
harmless: the counter is the part that distinguishes a working emitter from one
that has been silently failing.

#### Scenario: The lineage backend is unavailable

- **WHEN** the configured transport cannot deliver an event
- **THEN** the processing operation SHALL complete with unchanged results
- **AND** the failure SHALL be logged and reflected in a failure counter

#### Scenario: An emitter itself raises

- **WHEN** constructing or emitting an event raises
- **THEN** the exception SHALL NOT propagate into the data path
- **AND** the failure SHALL be counted like a transport failure

### Requirement: Dataset identity is derived from configuration, not from the host

Dataset namespaces and names SHALL be derived from configured endpoints and
identifiers. A runtime hostname, container id, process id or other
per-invocation value SHALL NOT appear in a dataset namespace or name.

Equivalent spellings of one endpoint SHALL normalise to one identity, so that a
single physical dataset does not appear under multiple aliases.

#### Scenario: The same table is addressed through different endpoint spellings

- **WHEN** two boundaries reference one dataset through endpoint spellings that
  differ only in scheme, credentials, port or trailing separators
- **THEN** both SHALL produce the same namespace and name

#### Scenario: A service restarts under a new container id

- **WHEN** an emitting service is recreated with a new container identity
- **THEN** the datasets it emits SHALL keep the identities they had before

### Requirement: A lineage run references identifiers the execution really had

A lineage run event SHALL carry the run identifiers available at that boundary
at execution time, and SHALL declare the ones it does not have as absent with a
reason rather than omitting or inventing them.

#### Scenario: A boundary lacks an orchestration identifier

- **WHEN** a long-running service emits lineage for work no orchestrator launched
- **THEN** the orchestration identifier SHALL be declared absent with its reason
- **AND** no substitute value SHALL be derived to fill it
