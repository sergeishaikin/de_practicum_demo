## ADDED Requirements

### Requirement: A metadata consumer preserves runtime lineage authority

When a catalog consumes OpenLineage events, it SHALL preserve the emitting
boundary as the sole authority for each runtime input/output edge. Catalog
ingestion SHALL NOT infer, backfill, or duplicate an edge from a different
connector merely because the relationship is visible in static metadata.

#### Scenario: Runtime and static metadata overlap

- **WHEN** dbt or a query-engine connector describes a relationship also present
  in an OpenLineage event
- **THEN** the runtime event remains attributed to its emitting boundary
- **AND** the static relationship is retained as a distinct, labelled topology
  source rather than a second runtime claim

### Requirement: Metadata entity aliases are deterministic

The catalog integration SHALL map configuration-equivalent dataset references to
one canonical service/catalog/schema/table identity. Host, container, process,
credential, and random execution identifiers SHALL NOT participate in the
canonical identity. An unresolved or ambiguous mapping SHALL be recorded as a
named gap and SHALL NOT create a guessed lineage edge.

#### Scenario: Trino and OpenLineage address one table

- **WHEN** Trino discovery and an OpenLineage event refer to the same configured
  Iceberg table using equivalent endpoint spellings
- **THEN** both references resolve to one entity
- **AND** the evidence records the normalisation inputs and resulting FQN

### Requirement: Catalog outage is fail-open and observable

Catalog delivery or ingestion failure SHALL NOT change the data-path result or
mutate processing checkpoints. The failure SHALL be logged and counted with a
bounded retry/timeout policy, and recovery SHALL be testable from a clean
profile state.

#### Scenario: Metadata backend is unavailable

- **WHEN** OpenMetadata, OpenSearch, or the metadata transport is unavailable
- **THEN** the existing producer or processing operation completes with its
  unchanged data semantics
- **AND** an observable failure record identifies the unavailable boundary

### Requirement: Preflight state is isolated and rebuildable

An OpenMetadata preflight SHALL use explicitly declared isolated state and
fixtures. It SHALL be destroyable and reproducible without resetting or
mutating canonical business topics, offsets, checkpoints, Iceberg tables, or
source databases.

#### Scenario: A preflight is rebuilt

- **WHEN** only the preflight profile state is removed and recreated
- **THEN** the same immutable images, fixture identities, entity mappings, and
  evidence checks are reproducible
- **AND** the core stack remains unchanged

### Requirement: Catalog compatibility supplements protocol representation only

WHEN an actual OpenLineage event references a dataset type that the selected
catalog cannot natively materialize, a metadata-consumer-side compatibility
adapter MAY create only a deterministic representation derived from that real
event.

The event SHALL remain runtime authority. The adapter SHALL preserve
`OpenLineage` source semantics where supported, SHALL not rewrite emitter
semantics or guess an upstream relationship, SHALL use deterministic identity,
and SHALL be idempotent on replay. It SHALL check for the native
representation first so future native catalog support suppresses the
supplement.

#### Scenario: Object-store input lacks native table mapping

- **WHEN** a real event contains an S3-compatible object-store input and an
  existing Iceberg output Table
- **THEN** the adapter may create a deterministic bucket/prefix Container and a
  Container → Table lineage representation
- **AND** the lineage details retain `source=OpenLineage` and event correlation

#### Scenario: Native support later exists

- **WHEN** the native connector already materialized the intended relationship
- **THEN** the adapter does nothing
- **AND** it creates no duplicate Container or lineage edge

#### Scenario: Unsupported or ambiguous input

- **WHEN** the event contains a malformed, unknown, non-object-store, or
  ambiguous DatasetRef
- **THEN** the adapter creates no guessed entity or edge

#### Scenario: Kafka input

- **WHEN** an event contains a Kafka input DatasetRef
- **THEN** the adapter SHALL NOT map it as a storage Container
