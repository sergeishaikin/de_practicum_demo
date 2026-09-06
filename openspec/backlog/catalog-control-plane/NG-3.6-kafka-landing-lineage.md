# NG-3.6 — Kafka-to-landing runtime lineage

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `close-kafka-landing-lineage-gap`
> **Authorization:** NONE

## Objective

Close the repository's explicitly documented lineage gap between the Kafka source boundary and the MinIO landing dataset so runtime lineage is continuous from Kafka through landing, Bronze, Silver and Gold.

## Scope

The change SHALL make the component that actually performs the Kafka-to-landing write own and emit that lineage edge through the existing OpenLineage boundary.

The implementation SHALL preserve the repository's lineage rules:

- an edge is emitted only by the job that actually performs the transformation/write;
- dataset names come from configured endpoints and stable logical identities, not container hostnames;
- emission remains fail-open with respect to the business data path;
- lineage identifiers remain aligned with `docs/PROVENANCE.md` and the canonical provenance vocabulary;
- no second lineage protocol is introduced.

## Non-goals

- Replacing OpenLineage or OpenMetadata.
- Inferring lineage by scanning object storage after the fact.
- Emitting an edge from another service merely because the relationship can be derived.
- Row-level lineage.
- Making OpenMetadata availability a correctness dependency of Kafka/Spark processing.

## Requirements

### Requirement: The Kafka-to-landing edge has one runtime owner

Exactly one first-party job SHALL own the emitted relationship from the configured Kafka orders dataset to the configured MinIO landing dataset.

### Requirement: The edge describes real execution

The lineage event SHALL be emitted from the runtime boundary that actually consumes Kafka and writes landing Parquet. It SHALL not be synthesized by the later Iceberg writer.

### Requirement: Lineage failure stays fail-open

An unavailable lineage backend SHALL be observable but SHALL NOT prevent successful Kafka consumption, checkpoint progression or landing writes.

### Requirement: Provenance fields remain canonical

Any new run/load/offset identifiers added to lineage facets SHALL use the repository's canonical provenance vocabulary and SHALL be absent-with-reason rather than fabricated when unavailable.

### Requirement: Existing downstream edges remain single-owned

Closing this gap SHALL NOT duplicate or reassign the existing landing-to-Bronze, Bronze-to-Silver or Silver-to-Gold edge ownership.

## Acceptance evidence

The archived change SHALL include:

- an emitted Kafka-to-landing OpenLineage event from the correct runtime owner;
- an OpenMetadata/UI or API proof showing the continuous path Kafka -> landing -> Bronze -> Silver -> Gold when the optional metadata profile is enabled;
- a negative test preventing duplicate ownership of the edge;
- a backend-outage test proving lineage emission failure does not fail the data path;
- provenance/offset evidence sufficient to correlate the lineage event with the actual streaming execution without leaking high-cardinality values into Prometheus labels.

## Rollback

The new lineage emission SHALL be removable without changing Kafka checkpoint state, landing file contents or downstream Iceberg data. Rollback restores the existing documented-gap state rather than inventing replacement lineage.

## Hard stops

Stop if:

- the actual Kafka-to-landing writer cannot be identified unambiguously from current code;
- emitting the edge would require a second owner for the same output dataset;
- the proposed implementation makes lineage delivery part of data-path success;
- the only available identifiers would have to be fabricated or inferred after the fact.

## Freshness of external assumptions

OpenLineage client behavior, Spark integration options and OpenMetadata ingestion compatibility SHALL be reverified at promotion. The repository's own standing lineage/provenance contracts are authoritative for local behavior and SHALL be reread before design.
