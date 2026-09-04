# NG-0.3 execution tasks

This task list records the actual sequence without retroactively claiming that
the final Milestone 3 plan existed during the Milestone 2 preflight.

## Milestone 2 — OM-PREFLIGHT

These tasks were the original preflight contract and remain completed
historical evidence.

### Design boundary

- [x] Re-read NG-0.3, the register, ADR-0003, governance, verification
  contract, NG-0.1 provenance, NG-0.2 runtime-lineage spec/evidence, and the
  current proposal.
- [x] Write `design.md` with hypotheses, evidence/pass-fail criteria, material
  blocker definition, DataHub trigger, authorities, aliases, resources, clean
  start, and rollback.
- [x] Write the initial `runtime-lineage` spec delta.
- [x] Write this task list and verify no Compose/application integration had
  started before the boundary.

### Wave A — candidate and compatibility evidence

- [x] Resolve the stable OpenMetadata server and ingestion release and record
  immutable registry digests.
- [x] Resolve OpenSearch and Postgres compatibility and record exact image
  identities for the isolated profile.
- [x] Capture primary-source requirements for Airflow, dbt, Kafka, Trino,
  OpenLineage, Iceberg, authentication, and resource sizing.
- [x] Compare repository versions/configuration with those requirements,
  including generated dbt artifacts and compiled SQL.

### Wave B — isolated control-plane preflight

- [x] Start only a temporary opt-in metadata profile with fresh declared
  volumes/networks and a dedicated metadata fixture namespace.
- [x] Prove metadata DB schema/user isolation, OpenSearch health/index/search,
  server/ingestion health, restart, and clean shutdown.
- [x] Measure startup, steady-state, peak memory/CPU, disk, and host headroom;
  keep vendor, repo allocation, and measured values separate.

### Wave C — connector and lineage probes

- [x] Probe Airflow through the existing deployment with read-only intent; do
  not add a second Airflow.
- [x] Ingest real dbt manifest/catalog/run-results artifacts and verify a
  representative model plus a required column-lineage subset.
- [x] Probe isolated Kafka topic metadata and a fixture event without changing
  business topics, offsets, or stale checkpoints.
- [x] Probe Trino/Iceberg discovery and verify canonical FQN aliasing.
- [x] Deliver one isolated OpenLineage event through Kafka using existing
  emitter semantics and verify transport parsing, run IDs, and no duplicate
  edge authority. Full indexed event-edge ownership remained Milestone 3 work
  at this historical checkpoint.

### Wave D — guardrails and decision

- [x] Verify secret redaction/read-only permissions and catalog-outage fail-open
  behaviour with an observable counter/log.
- [x] Destroy only the preflight profile and rebuild from clean state; compare
  identity, search, lineage, and artifact results.
- [x] Record unsupported connectors, unresolved datasets, and the NG-0.2
  streaming gap as explicit limitations rather than inferred edges.
- [x] Produce the OM-PREFLIGHT report with exactly one exit classification.
- [x] Stop and wait for operator `CONTINUE`; the operator later supplied the
  explicit continuation authorization before Milestone 3 implementation.

## Milestone 3 — implementation and local acceptance

The following work was implemented and accepted after the Milestone 2
checkpoint. It is represented here as completed current truth.

- [x] Add the permanent optional metadata profile with immutable image pins.
- [x] Isolate metadata persistence and preserve the no-second-Airflow boundary.
- [x] Configure source connectors for PostgreSQL, Airflow, Kafka, Trino/Iceberg,
  OpenLineage, and both dbt artifact surfaces.
- [x] Add deterministic dbt 1.12.2 artifact compatibility guards.
- [x] Add reproducible ownership/domain seeding and explicit BI coverage gaps.
- [x] Configure OpenLineage Kafka transport without changing writer semantics.
- [x] Index real Bronze → Silver and Silver → Gold runtime lineage.
- [x] Prove the real writer landing → Bronze OpenLineage event.
- [x] Implement the narrow object-store Container compatibility adapter.
- [x] Add native-edge suppression, deterministic identity, replay idempotency,
  and negative dataset-type tests.
- [x] Prove duplicate-entity search, UI/API acceptance, and impact analysis.
- [x] Execute metadata/OpenSearch/consumer failure injection and record
  fail-open behaviour.
- [x] Record the measured local resource receipt and metadata-only rebuild.
- [x] Run security/secret checks and read-only PostgreSQL probes.
- [x] Update catalog, lineage, and acceptance documentation.
- [x] Add focused adapter and metadata contract tests.
- [x] Capture Gold overview/lineage and landing Container lineage evidence plus
  the sanitized API receipt.
- [x] Complete the local acceptance receipt: `MILESTONE 3 STATUS: COMPLETE`.
- [x] Push implementation/documentation commits, including `04f0402`.

## Milestone 3B — OpenSpec reconciliation

- [x] Re-read the active change, backlog, standing specs, implementation,
  tests, and acceptance receipt.
- [x] Promote the historical preflight design into a separate final implemented
  design section without rewriting history.
- [x] Restructure this task list into Milestones 2, 3, 3B, and 4.
- [x] Consolidate Milestone 2 and Milestone 3 evidence into `evidence.md`.
- [x] Add the standing `metadata-catalog` spec delta with current product
  behaviour and acceptance scenarios.
- [x] Update the `runtime-lineage` delta with the bounded compatibility-adapter
  contract and native-support guard.
- [x] Check proposal/design/tasks/evidence/spec/docs for stale current-truth
  contradictions while preserving historical statements.
- [x] Run strict OpenSpec validation, backlog validation, focused lifecycle and
  metadata-contract tests, and `git diff --check`.
- [x] Commit and push this reconciliation before archive.

## Milestone 4 — closure

These tasks record the completed governed closure step.

- [x] Run final local repository completion gates.
- [x] Run final metadata-profile acceptance required by the verification
  contract.
- [x] Push closure-ready state if required.
- [x] Observe required live CI workflows.
- [x] Diagnose failures causally; no retry-until-green.
- [x] Consolidate final `evidence.md`.
- [x] Merge/apply spec deltas to standing truth through normal OpenSpec archive.
- [x] Update NG-0.3 lifecycle/disposition to `DONE` / `ADOPTED`.
- [x] Archive `add-openmetadata-catalog`.
- [x] Validate archived lifecycle state.
- [x] Verify zero active change for NG-0.3.
- [x] Verify a clean tree.
- [x] Stop for operator Milestone 4 review before starting NG-0.4.
