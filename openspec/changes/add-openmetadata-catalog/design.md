# NG-0.3 design record

## Preflight decision

Status: complete historical Milestone 2 decision boundary; superseded for
current implementation description by the final design below.
Milestone: 2 (OM-PREFLIGHT)
Change: `add-openmetadata-catalog`
Decision gate: this document must be accepted by the evidence collected in the
preflight before any production Compose/profile or emitter change is made.

## Decision question

Can OpenMetadata be adopted as the NG-0.3 metadata consumer for this repository,
with the existing Airflow/dbt/Kafka/Trino/Iceberg/OpenLineage boundaries kept
authoritative, within a reproducible opt-in profile and an explicitly measured
local resource envelope? If a material capability is disproved, is DataHub a
credible fallback rather than an automatic second implementation?

The preflight is an architectural decision, not a container smoke test. Every
claim below needs a primary-source reference, a repository reference, or a
repeatable local observation. A cached image is a candidate only; the accepted
identity is an immutable digest proved against the upstream registry.

## Candidate and architecture hypotheses

The following are hypotheses to test, not approvals to deploy.

| ID | Hypothesis | PASS evidence | FAIL / material blocker |
| --- | --- | --- | --- |
| H1 | OpenMetadata server `1.13.3` is a current stable candidate and can start with the repository's supported Java/Postgres/OpenSearch combination. | Upstream release identity, immutable server/ingestion digests, healthy API/UI, startup from isolated state. | No reproducible start, incompatible dependency, or only a pre-release image is usable. |
| H2 | Metadata persistence can be isolated from the core data plane. | Dedicated database and user (or a dedicated metadata DB container if required), least-privilege connection, no schema/table writes to canonical `airflow`/warehouse databases. | Any required shared superuser access or metadata writes into canonical state. |
| H3 | OpenSearch `3.3.x` is compatible and reproducible for this candidate. | Immutable digest, health, index creation/search, restart without index loss. | Search incompatibility, undocumented floating image, or unrecoverable index state. |
| H4 | Airflow coverage is available without introducing a second Airflow. | Connector/API probe resolves the existing Airflow deployment and records DAG/task metadata with read-only credentials and no scheduler replacement. | Connector cannot reach the supported repository Airflow line, or requires a second scheduler. |
| H5 | The real repository dbt artifacts can produce model and required column lineage. | `manifest.json` plus `catalog.json`/`run_results.json` from the actual warehouse project are accepted; compiled SQL and a sampled column edge are visible and repeatable. | Artifacts are stale/unavailable, dbt version is unsupported without an explicit adapter, or the required column subset cannot be evidenced. |
| H6 | Kafka metadata can be ingested read-only. | Dedicated metadata connector credentials list the isolated fixture topics and schemas/partitions where supported, with no mutation of business topics or offsets. | Connector requires write/admin access beyond scope or cannot identify the fixture dataset. |
| H7 | Trino is the physical catalog authority for Iceberg tables. | Read-only connector discovers the configured catalog/schema/table and links it to the same canonical dataset identity used by runtime lineage. | Tables cannot be resolved, require unsafe permissions, or aliases split one physical table into multiple entities. |
| H8 | Existing OpenLineage emitters can feed the catalog by transport configuration, without semantic emitter rewrites. | Kafka transport dependency/configuration is proven, an isolated event reaches OpenMetadata, and the event's input/output edges remain attributable to the emitting boundary. | Kafka transport is incompatible, requires changing event semantics, or the catalog fabricates/duplicates edges. |
| H9 | Secrets and outage behaviour satisfy the governance contract. | Secrets are injected through env/file indirection, never committed; catalog outage leaves data paths unchanged and emits an observable failure; read-only source credentials are verified. | Plaintext secret requirement, outage changes data semantics, or credentials need destructive scope. |
| H10 | The opt-in profile is reproducible and worth its local cost. | Clean start, health, indexed search, lineage/UI value, destroy/rebuild, and a three-way resource receipt (vendor docs vs repo allocation vs measured local use). | Core stack changes without profile, rebuild drift, or resource demand materially exceeds the declared environment without an accepted limitation. |

## Architectural invariants to validate

### Profile and state

The metadata stack is an opt-in Compose profile. The default core command must
remain behaviourally unchanged. OpenMetadata, OpenSearch, and metadata
persistence use isolated service names, networks/volumes, and fixture data. A
preflight run must start from fresh metadata volumes and isolated Kafka topics,
consumer groups, checkpoints, and temporary artifact locations. Existing stale
streaming checkpoints and volumes are **out of scope**: do not reset offsets,
change `failOnDataLoss`, or mutate canonical state to make a test pass.

Rollback is deletion of only the preflight profile's declared containers,
networks, volumes, topics, consumer groups, and temporary artifacts. The core
Compose files, business topics, Iceberg tables, and source databases must be
left intact and verifiably unchanged.

### Persistence and search

The preferred architecture is a dedicated metadata database/user on an
explicitly isolated Postgres database when permissions and schema isolation are
proved. A dedicated metadata Postgres container is an acceptable alternative if
the existing server cannot provide that isolation without elevated access. The
OpenSearch service is internal to the metadata profile. The chosen option must
be recorded with connection, permission, restart, and rebuild evidence.

### Lineage authority and aliasing

* Runtime OpenLineage edges are authoritative only for datasets actually read
  and written by the emitting boundary. The catalog is a consumer, never a
  second runtime-edge authority.
* dbt artifacts are authoritative for static model dependency and column
  topology; dbt tests/status are accepted only when backed by `run_results.json`.
* Trino is the physical entity authority for Iceberg tables; the Iceberg REST
  catalog is not treated as a separate lineage source.
* Airflow owns orchestration metadata; Kafka owns messaging/topic metadata.
* Canonical entity identity is configuration-derived and normalised to one
  service/catalog/schema/table FQN. Hostnames, container IDs, random run IDs,
  credentials, and endpoint spelling differences must not create aliases.
  Every unresolved or ambiguous mapping is recorded as a gap; no guessed edge
  is accepted. Duplicate ownership claims are a FAIL for that hypothesis.

### Transport and compatibility

The preflight may configure an isolated OpenLineage Kafka transport, but must
not rewrite emitter semantics or alter processing behaviour. Any required
Kafka client dependency is pinned in the repository lock/requirements only
after a bounded compatibility probe demonstrates the import and delivery path.
The event topic, consumer group, retention, and fixture namespace are dedicated
to preflight and are never allowed to consume or mutate stale production-like
checkpoints.

### Resource measurement

The receipt reports three separate numbers for each component:

1. vendor-documented requirement (with source/version and whether it is
   production or minimum sizing);
2. repository Compose allocation/limits and image/storage allocation; and
3. measured local peak/steady CPU, memory, disk, startup time, and host headroom
   on the declared Docker engine.

Conflicting vendor tables are retained as separate contexts, not silently
averaged. The verdict is based on measured reproducibility plus an explicit
limitation if the local host cannot represent a production envelope.

## Evidence plan

Evidence is collected in this order:

1. immutable image manifests, release/version compatibility, and primary-source
   connector requirements;
2. isolated metadata DB/search startup and health;
3. read-only connector probes for Airflow, dbt, Kafka, Trino/Iceberg;
4. isolated OpenLineage event delivery and identity/column-lineage checks;
5. security/outage probes, clean destroy/rebuild, UI/search value, and resource
   measurement.

Each probe records command, timestamp, image digest, fixture identity, result,
and a link to the saved log. A failed probe is retained; retries may not erase
the first failure. No full integration is started before this design and task
list exist in the change directory.

## Material blocker and DataHub fallback

A material blocker is a failure of H1-H9 that prevents a required NG-0.3
capability (metadata persistence/search, runtime lineage ingestion, canonical
dataset resolution, required dbt column subset, or safe reproducibility), or a
security/resource constraint that cannot be isolated with a documented
limitation. A cosmetic UI gap, an optional connector, or the already-labelled
NG-0.2 streaming lineage gap is not material by itself.

DataHub is evaluated only when a material OpenMetadata blocker is evidenced. The
fallback comparison must use the same authority, identity, security, resource,
and reproducibility criteria; it must not be deployed speculatively during this
preflight. If no material blocker exists, OpenMetadata remains the selected
candidate and the milestone ends without a DataHub stack.

## Exit classifications

The milestone report must end with exactly one of:

* `PASS` — all required hypotheses pass and the implementation may be planned;
* `PASS_WITH_EXPLICIT_LIMITATIONS` — required path passes, and every remaining
  limitation has an owner, evidence, and non-misleading UI/documentation rule;
* `FAIL_MATERIAL_OPENMETADATA_GAP` — OpenMetadata cannot provide a required
  capability; DataHub fallback is evaluated and the milestone stops;
* `FAIL_ENVIRONMENT` — the candidate is viable but this environment cannot run
  the isolated proof reproducibly;
* `FAIL_SPEC_CONTRADICTION` — repository governance/specs cannot be satisfied
  simultaneously without operator direction.

The historical Milestone 2 gate required an explicit operator `CONTINUE` after
the completed report. That checkpoint was subsequently satisfied before
Milestone 3 implementation; it is retained here to preserve the actual
authorisation sequence rather than implying that the final design existed
before implementation.

## Final implemented design

Milestone 3 implementation and local acceptance completed through commit
`04f0402`. This section describes the current contract, not the earlier
preflight hypothesis.

### Control plane

- The metadata plane is an optional `metadata` Compose profile.
- OpenMetadata server and ingestion use immutable 1.13.3 image digests.
- OpenSearch 3.3.0 uses an immutable image digest.
- Metadata persistence uses isolated PostgreSQL state and credentials.
- A bounded ingestion worker/process runs the official workflows and the
  narrow compatibility adapter; no second repository Airflow scheduler is
  introduced.

### Metadata sources

The implemented inventory consumes, where supported, the warehouse PostgreSQL
schemas, existing Airflow API, Kafka topic metadata, Trino/Iceberg physical
tables, both warehouse and semantic dbt artifact surfaces, and the available BI
coverage. Unsupported or incomplete surfaces remain explicit in
`docs/CATALOG-ACCEPTANCE.md`; the rendered report is not presented as a BI
connector.

### Runtime lineage

NG-0.2 remains runtime authority. Real OpenLineage events travel through the
dedicated Kafka lineage topic and the official OpenMetadata OpenLineage
ingestion workflow remains primary. The accepted indexed path is:

```text
landing -> Bronze -> Silver -> Gold
```

The event and edge ownership are not rewritten by the catalog.

### Object-store compatibility adapter

The selected implementation is Option A: declarative, metadata-consumer-side
materialization only.

```text
real OpenLineage object-store DatasetRef
    -> deterministic StorageService/Container
    -> Container -> existing Table lineage representation
```

The writer event is unchanged and remains the runtime authority. The adapter
preserves `lineageDetails.source=OpenLineage`, records job/run/input
correlation, normalizes `s3://`, `s3a://`, and `s3n://`, and derives identity
from bucket plus collision-safe prefix encoding. Runtime IDs, credentials,
hosts, and container IDs never participate in entity identity. Replays are
idempotent. Before supplementing an event, the adapter checks for a native
edge; future native OpenMetadata support therefore suppresses the supplement.
Unknown, malformed, non-object-store, and Kafka inputs are ignored rather than
guessed, and no landing Table or manually maintained runtime edge is created.

### Authority model

- OpenLineage: runtime first-party boundaries and runtime edges.
- dbt artifacts: static model topology, column topology, and dbt test metadata.
- Trino: physical Iceberg entity discovery.
- Airflow: pipeline and orchestration metadata.
- Kafka connector: messaging asset metadata.
- OpenMetadata: catalog consumer and presentation layer.

### Dataset identity

Canonical entity identity is configuration-derived. Equivalent endpoint
spellings resolve to one entity; Container names encode prefixes without slash
versus underscore collisions, while the original prefix remains in `prefix`
and `fullPath`. UUIDs are catalog implementation identifiers, not the logical
identity contract.

### Ownership and domains

Ownership and domain assignments are seeded from checked-in configuration,
not manually entered UI state. The acceptance receipt records the reproducible
mapping for the core physical assets.

### Credentials

The metadata PostgreSQL reader role passed negative write probes. Airflow's
local SimpleAuthManager remains an all-admin demo limitation, Trino is local
unauthenticated, and Kafka is local PLAINTEXT; these are explicit limitations,
not universal least-privilege claims.

### Failure behavior

Metadata/control-plane outage is fail-open for the data plane. The outage
receipt covers metadata server, OpenSearch, and OpenLineage consumer
interruptions; writer and medallion processing remained running and recovered.

### Rebuild

Metadata-only destroy/rebuild reconstructs stable FQNs, ownership, domains,
discoverable assets, and lineage without changing canonical Kafka, PostgreSQL,
or Iceberg state. Metadata UUIDs may change on rebuild and are not a stable
contract.

### Resource model

The measured local permanent profile is recorded separately from vendor
production guidance in `openspec/changes/add-openmetadata-catalog/evidence.md`.
The local measurement is evidence for this demo, not production sizing
approval.

### Intentional remaining gap

The only intentional remaining lineage gap is:

```text
Kafka -> Spark -> landing
```

It remains outside the NG-0.2 compatibility boundary because the repository's
Spark 4.2 runtime has no proven compatible OpenLineage Spark integration build.

### Historical sequence and governance correction

Milestone 2 preflight design existed first; the operator reviewed and approved
that preflight, then explicitly authorised Milestone 3 continuation. Milestone
3 implementation and acceptance were completed. A later review found that the
active design, tasks, and evidence files had remained preflight-scoped. This
Milestone 3B section reconciles the active change before archive without
rewriting earlier commits or claiming that the final implementation design was
present before implementation.
