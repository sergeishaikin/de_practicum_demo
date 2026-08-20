# OM-PREFLIGHT tasks

This task list is the execution contract for Milestone 2. It is intentionally
bounded to evidence and architecture. It does not authorise the Milestone 3
implementation.

## Design boundary (complete before integration)

- [x] Re-read NG-0.3, the register, ADR-0003, governance, verification
  contract, NG-0.1 provenance, NG-0.2 runtime-lineage spec/evidence, and the
  current proposal.
- [x] Write `design.md` with hypotheses, evidence/pass-fail criteria, material
  blocker definition, DataHub trigger, authorities, aliases, resources, clean
  start, and rollback.
- [x] Write the required `runtime-lineage` spec delta.
- [x] Write this task list and verify no Compose/application integration has
  started before the boundary.

## Wave A — candidate and compatibility evidence

- [x] Resolve the current stable OpenMetadata server and ingestion release and
  record immutable registry digests; distinguish stable from pre-release.
- [x] Resolve OpenSearch and Postgres compatibility and record the exact image
  identities selected for the isolated profile.
- [x] Capture primary-source requirements for Airflow, dbt, Kafka, Trino,
  OpenLineage, Iceberg, authentication, and resource sizing.
- [x] Compare repository versions and configuration with those requirements,
  including the actual generated dbt artifacts and compiled SQL.

## Wave B — isolated control-plane preflight

- [x] Start only a temporary, opt-in metadata profile with fresh declared
  volumes/networks and a dedicated metadata fixture namespace.
- [x] Prove metadata DB schema/user isolation, OpenSearch health/index/search,
  server/ingestion health, restart, and clean shutdown.
- [x] Measure startup, steady-state, peak memory/CPU, disk, and host headroom;
  keep vendor, repo allocation, and measured values separate.

## Wave C — connector and lineage probes

- [x] Probe Airflow metadata through the existing deployment using read-only
  access; do not add a second Airflow.
- [x] Ingest the real dbt manifest/catalog/run-results artifacts and verify a
  representative model plus a required column-lineage subset.
- [x] Probe isolated Kafka topic metadata and a fixture event without changing
  business topics, offsets, or stale checkpoints.
- [x] Probe Trino/Iceberg discovery and verify canonical FQN aliasing.
- [x] Deliver one isolated OpenLineage event through Kafka using existing
  emitter semantics and verify runtime-edge ownership, run IDs, and no duplicate
  edge authority.

## Wave D — guardrails and decision

- [x] Verify secret redaction/read-only permissions and catalog-outage fail-open
  behaviour with an observable counter/log.
- [x] Destroy only the preflight profile and rebuild from clean state; compare
  identity, search, lineage, and artifact results.
- [x] Record every unsupported connector, unresolved dataset, and the existing
  NG-0.2 streaming gap as explicit limitations rather than inferred edges.
- [x] Produce the full OM-PREFLIGHT report with evidence matrices and exactly
  one exit classification from `design.md`.
- [ ] Stop and wait for operator `CONTINUE`; do not implement Milestone 3 in
  this milestone.
