## ADDED Requirements

### Requirement: Metadata catalog is an optional control plane

The catalog SHALL be provided by an opt-in metadata profile. The default/core
Compose graph SHALL remain usable without that profile, and catalog operations
SHALL NOT write canonical business data.

#### Scenario: Core stack runs without metadata

- **WHEN** the metadata profile is not selected
- **THEN** the core services retain their existing behavior
- **AND** no metadata service is required for data processing

#### Scenario: Catalog is unavailable during processing

- **WHEN** OpenMetadata or its search backend is unavailable
- **THEN** writer and medallion data semantics remain unchanged
- **AND** the failure is observable at the metadata boundary

### Requirement: Catalog persistence is isolated

Metadata application state SHALL use dedicated persistence and credentials. The
search backend SHALL be internal to the metadata profile and SHALL NOT be used
as a business data store.

#### Scenario: Metadata state is rebuilt

- **WHEN** only metadata database/search state is removed
- **THEN** canonical Kafka, PostgreSQL warehouse, and Iceberg state is unchanged
- **AND** the catalog can be rebuilt from source metadata, artifacts, events, and
  configuration

### Requirement: Existing orchestration remains authoritative

The catalog SHALL read the existing Airflow deployment through its supported
API and SHALL NOT introduce a second repository Airflow scheduler.

#### Scenario: Airflow metadata is ingested

- **WHEN** the catalog indexes repository DAG metadata
- **THEN** the existing Airflow deployment remains the orchestration authority
- **AND** no replacement scheduler is started

### Requirement: Catalog core asset coverage is explicit

The catalog SHALL classify coverage for PostgreSQL, Airflow, Kafka,
Trino/Iceberg, dbt, and available BI assets. Unsupported or partial assets SHALL
be named as gaps rather than silently omitted from an end-to-end claim.

#### Scenario: A BI connector is unavailable

- **WHEN** the selected BI platform has no configured catalog connector
- **THEN** BI coverage is recorded as an explicit limitation
- **AND** a rendered report SHALL NOT be presented as connector-backed lineage

### Requirement: dbt artifacts are deterministic inputs

The catalog SHALL consume reproducibly generated dbt artifacts for model,
documentation, test, freshness, and column topology. dbt SHALL remain execution
and result authority.

#### Scenario: dbt artifacts are indexed

- **WHEN** a dbt manifest/catalog/run-results set is ingested
- **THEN** its version and artifact paths are checked by the repository guard
- **AND** OpenMetadata presentation does not create a competing dbt execution
  result

### Requirement: Column lineage claims are evidence-backed

Column-level lineage SHALL be shown only when the producing connector or dbt
artifacts provide the relationship. Table-level runtime lineage SHALL NOT be
converted into synthetic column edges.

#### Scenario: Runtime input has no column facet

- **WHEN** an OpenLineage event proves only a table-level relationship
- **THEN** the catalog records table-level lineage
- **AND** it does not invent column-level lineage

### Requirement: Runtime lineage is consumed from OpenLineage

OpenLineage events and their emitting boundaries SHALL remain runtime authority.
The official OpenMetadata OpenLineage ingestion path SHALL remain primary. A
product-specific compatibility representation MAY supplement protocol-derived
metadata only when the selected catalog cannot natively represent the actual
dataset type.

#### Scenario: Object-store input lacks native table mapping

- **WHEN** a real OpenLineage event contains an object-store DatasetRef and an
  existing Iceberg output Table
- **THEN** a catalog-side adapter MAY create a deterministic StorageService and
  Container and a Container → Table representation
- **AND** the event remains the runtime authority with `source=OpenLineage`

#### Scenario: Native support later exists

- **WHEN** the native catalog connector already materialized the intended edge
- **THEN** the compatibility adapter does nothing
- **AND** no duplicate entity or edge is created

#### Scenario: Unsupported or ambiguous input is received

- **WHEN** an input is malformed, unknown, ambiguous, or not the proven
  object-store case
- **THEN** the adapter creates no guessed entity or edge

#### Scenario: Kafka input reaches the adapter

- **WHEN** an event contains a Kafka input DatasetRef
- **THEN** it is never mapped as an object-store Container

### Requirement: Dataset identity is deterministic and rebuildable

Equivalent object-store spellings SHALL normalize to one bucket/prefix identity.
Credentials, hosts, run IDs, process IDs, and catalog UUIDs SHALL NOT become
identity components. Prefix encoding SHALL avoid slash/underscore collisions.

#### Scenario: Equivalent S3 spellings are replayed

- **WHEN** `s3://`, `s3a://`, and `s3n://` refer to the same bucket/prefix
- **THEN** they resolve to the same Container identity
- **AND** replay is idempotent

### Requirement: Ownership and domains are reproducible

Critical ownership and domain metadata SHALL come from checked-in or otherwise
reproducible configuration rather than UI-only edits.

#### Scenario: Metadata state is recreated

- **WHEN** the catalog profile is rebuilt
- **THEN** the same logical assets receive the same configured ownership/domain
  assignments

### Requirement: Source access is minimum/read-only where supported

Source connectors SHALL use read-only or metadata-minimum privileges where the
source supports them. Local exceptions such as Airflow SimpleAuthManager,
unauthenticated Trino, and PLAINTEXT Kafka SHALL be documented explicitly.

#### Scenario: Reader permissions are probed

- **WHEN** the metadata reader is tested against PostgreSQL
- **THEN** destructive/write operations are denied
- **AND** any local limitation is recorded rather than generalized away

### Requirement: User-visible impact analysis is evidence-backed

A representative Gold asset SHALL support evidence-backed search, schema,
ownership/domain, upstream and downstream lineage to the extent proven by the
configured connectors and runtime events.

#### Scenario: Operator opens the Gold asset

- **WHEN** an operator opens `gold.orders_daily_metrics`
- **THEN** the UI shows the indexed schema and ownership/domain context
- **AND** the accepted Bronze/Silver/Gold lineage and downstream context are
  visible where supported

### Requirement: Resource claims are scoped

Local resource measurements SHALL be labelled as demo evidence and kept
separate from vendor production sizing guidance. A local profile measurement
SHALL NOT be presented as production capacity approval.

#### Scenario: Local resource receipt is reported

- **WHEN** the metadata profile's memory/CPU use is recorded
- **THEN** the report identifies the host and capture context
- **AND** vendor guidance and local measurements remain separate
