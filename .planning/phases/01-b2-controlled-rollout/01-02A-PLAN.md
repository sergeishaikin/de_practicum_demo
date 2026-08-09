---
phase: 01-b2-controlled-rollout
plan: 02A
type: execute
wave: 3
depends_on: [01-02]
files_modified:
  - artifacts/b2-rollout/02a-catalog-diagnosis.json
  - artifacts/b2-rollout/02a-catalog-concurrency.log
  - artifacts/b2-rollout/02a-catalog-recovery.json
  - artifacts/b2-rollout/02a-sqlite-backup.sha256
  - artifacts/b2-rollout/02a-sqlite-catalog.db
  - artifacts/b2-rollout/02a-catalog-before.json
  - artifacts/b2-rollout/02a-catalog-after.json
  - artifacts/b2-rollout/02a-catalog-equivalence.json
  - artifacts/b2-rollout/02a-concurrency-proof.log
  - docs/runtime/H1-reproducible-runtime.md
autonomous: true
requirements: [CAN-01]
must_haves:
  truths:
    - "The SQLite catalog lock path and concurrent committers are identified from service evidence, not inferred from a retry loop."
    - "The catalog persistence backend used by the rollout supports concurrent writer, medallion, Trino, and dbt access without SQLITE_BUSY failures."
    - "Catalog data is preserved; no catalog volume reset, table recreation, or Iceberg data deletion is used as a fix."
    - "The PostgreSQL catalog registration points to the exact existing Iceberg metadata_location for every table."
    - "Before and after inventories prove identical table UUID, snapshot, schema, partition spec, sort order, and metadata_location for every table."
    - "No Iceberg data file, metadata file, snapshot, or catalog registration is rewritten as part of the migration."
  artifacts:
    - path: "artifacts/b2-rollout/02a-catalog-diagnosis.json"
      provides: "Before/after backend, lock errors, active clients, and preservation evidence"
      contains: "sqlite_backend, concurrent_committers, data_preserved"
    - path: "artifacts/b2-rollout/02a-catalog-recovery.json"
      provides: "Focused concurrent catalog recovery result"
      contains: "passed"
    - path: "artifacts/b2-rollout/02a-catalog-equivalence.json"
      provides: "Machine-readable old/new catalog equality receipt"
      contains: "metadata_location, table_uuid, current_snapshot_id, schema, partition_spec, sort_order"
    - path: "artifacts/b2-rollout/02a-sqlite-backup.sha256"
      provides: "Checksum of the preserved pre-migration SQLite catalog backup"
      contains: "iceberg_catalog.db"
  key_links:
    - from: "docker-compose.extended.yml"
      to: "de-demo-iceberg-rest"
      via: "catalog persistence configuration"
      pattern: "CATALOG_URI"
    - from: "de-demo-iceberg-writer/de-demo-iceberg-medallion"
      to: "de-demo-iceberg-rest"
      via: "REST catalog commits"
      pattern: "ICEBERG_CATALOG_URI"
---

<objective>
Close the confirmed Iceberg REST catalog concurrency blocker before another B2 canary.

Purpose: replace the current SQLite-backed catalog state with a durable concurrent backend
supported by the runtime, while preserving the existing REST API, PyIceberg/Trino ownership,
Iceberg warehouse, Bronze/Silver/Gold data, and rollout boundaries.
</objective>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
@.planning/phases/01-b2-controlled-rollout/CONTEXT.md
@artifacts/b2-rollout/02-canary-receipt.json
@artifacts/b2-rollout/02-canary-rollback.txt
@docker-compose.extended.yml
@.env.example
@.env.extended.example
@tests/test_h1_runtime.py
@tests/integration/test_iceberg_trino.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Capture the SQLite failure and all catalog committers</name>
  <files>artifacts/b2-rollout/02a-catalog-diagnosis.json, artifacts/b2-rollout/02a-catalog-concurrency.log</files>
  <action>Keep the safe runtime tuple legacy/legacy/0 and quiesce every catalog writer before taking the migration baseline. Capture the active catalog image/container configuration, CATALOG_URI, catalog volume identity, REST logs, and the process/query clients that can commit catalog metadata (writer, medallion, Trino, dbt). Make a preserved copy of the existing SQLite database and calculate its SHA-256 checksum; do not modify or delete the original. Capture a machine-readable inventory for every existing Iceberg table: namespace, identifier, metadata_location, table UUID, current snapshot ID, schema ID/schema, partition spec, sort order, and snapshot history/count where available. Reproduce or use the 01-02 evidence to record the exact SQLITE_BUSY/UncheckedSQLException path. Do not add sleeps, infinite retries, exception suppression, or permanent quiescing of a required client. Do not delete or recreate the catalog volume.</action>
  <verify><automated>docker inspect de-demo-iceberg-rest --format '{{range .Config.Env}}{{println .}}{{end}}'; docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml logs --no-color --since 30m iceberg-rest iceberg-writer iceberg-medallion trino; python -c "import json; p=json.load(open('artifacts/b2-rollout/02a-catalog-diagnosis.json')); assert p['sqlite_backend'] is True; assert p['data_preserved'] is True; assert p['concurrent_committers']; print('catalog diagnosis PASS')"; Test-Path artifacts/b2-rollout/02a-sqlite-backup.sha256; Test-Path artifacts/b2-rollout/02a-catalog-before.json</automated></verify>
  <done>The failure path, concurrent committers, catalog volume, and preservation baseline are recorded.</done>
</task>

<task type="auto">
  <name>Task 2: Move catalog metadata to a durable concurrent backend</name>
  <files>docker-compose.extended.yml, .env.example, .env.extended.example, artifacts/b2-rollout/02a-catalog-recovery.json</files>
  <action>Use the repository's existing Postgres service or another runtime-supported JDBC backend for Iceberg REST catalog metadata, with credentials sourced from the existing env examples and local .env. Quiesce all catalog writers, preserve the SQLite backup/checksum, and capture a rollback configuration before changing the backend. Implement the smallest configuration change that removes SQLite as runtime catalog authority while preserving the REST endpoint and warehouse. Migrate/import catalog registrations so they continue to point to the exact existing metadata_location values. Do not create replacement Iceberg tables; do not rewrite Iceberg data files or metadata files; do not advance snapshots; do not initialize an empty PostgreSQL catalog and call it migrated. If the image/runtime cannot safely migrate the registrations, stop and record the exact blocker instead of changing the active catalog. After migration, capture the same machine-readable inventory and produce an equivalence receipt requiring exact equality for namespace/identifier, metadata_location, table UUID, current snapshot ID, schema, partition spec, sort order, and snapshot history/count where available. Verify Bronze/Silver counts and logical invariants, NULL business_version=0, Silver uniqueness, Silver==accepted B2 projection, and dbt 26/26. Then run real overlapping writer/medallion/Trino/dbt catalog activity; require no UncheckedSQLException, no database locking failure, no lost catalog update, and no metadata pointer divergence. A bounded retry may remain only as defense-in-depth after the backend fix and must not be the claimed root-cause fix.</action>
  <verify><automated>docker compose --env-file .env -f docker-compose.yml -f docker-compose.extended.yml config --quiet; python scripts/validate_runtime_config.py --env-file .env --profile local; python -m pytest -q --basetemp .pytest-catalog tests/test_h1_runtime.py tests/integration/test_iceberg_trino.py; python -c "import json; p=json.load(open('artifacts/b2-rollout/02a-catalog-recovery.json')); e=json.load(open('artifacts/b2-rollout/02a-catalog-equivalence.json')); assert p['passed'] is True; assert p['sqlite_busy_errors']==0; assert p['data_preserved'] is True; assert e['passed'] is True; assert e['all_tables_equal'] is True; assert e['metadata_files_rewritten']==0; assert e['data_files_rewritten']==0; assert e['snapshots_advanced']==0; print('catalog recovery and metadata equivalence PASS')"; python -m dbt parse --project-dir dbt --profiles-dir dbt; python -m dbt test --project-dir dbt --profiles-dir dbt</automated></verify>
  <done>A non-SQLite concurrent catalog backend is active and verified, or the plan fails closed with a precise unsupported-migration receipt; no empty replacement catalog is accepted.</done>
</task>

</tasks>

<success_criteria>
02A is green only when the preserved SQLite backup/checksum exists, before/after inventories prove exact metadata equivalence for every table, no data/metadata files or snapshots were changed, Bronze/Silver/dbt invariants remain green, and overlapping runtime clients complete without lock failures or pointer divergence. A migration blocker stops the rollout and leaves legacy/legacy/0 active. This plan does not touch Kafka checkpoints, restart the B2 canary, execute 01-02B, or execute 01-03/later plans.
</success_criteria>

<output>Create .planning/phases/01-b2-controlled-rollout/01-02A-SUMMARY.md when done.</output>
