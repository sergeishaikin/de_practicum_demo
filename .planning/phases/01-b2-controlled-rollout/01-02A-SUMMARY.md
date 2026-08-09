---
phase: 01-b2-controlled-rollout
plan: 02A
subsystem: iceberg-catalog
tags: [iceberg, rest-catalog, postgresql, sqlite, migration, concurrency]
requires: [01-02]
provides: [postgres-backed-rest-catalog, metadata-equivalence-receipt, catalog-concurrency-proof]
affects: [writer, medallion, trino, dbt]
tech-stack:
  added: []
  patterns: [metadata-preserving-catalog-registration-migration]
key-files:
  created:
    - artifacts/b2-rollout/02a-sqlite-backup.sha256
    - artifacts/b2-rollout/02a-sqlite-catalog.db
    - artifacts/b2-rollout/02a-catalog-before.json
    - artifacts/b2-rollout/02a-catalog-after.json
    - artifacts/b2-rollout/02a-catalog-equivalence.json
    - artifacts/b2-rollout/02a-concurrency-proof.log
    - artifacts/b2-rollout/02a-catalog-recovery.json
  modified:
    - docker-compose.extended.yml
    - .env.example
    - docs/runtime/H1-reproducible-runtime.md
requirements-completed: [CAN-01]
duration: 2h
completed: 2026-08-09
---

# Phase 1 Plan 02A: PostgreSQL Catalog Migration Summary

Replaced the persistent SQLite-backed Iceberg REST catalog authority with PostgreSQL registrations that point to the exact existing Iceberg metadata, preserving data and snapshot identity.

## Outcome

- SQLite catalog backup preserved in Docker volume `de_demo_iceberg_catalog_backup_02a`.
- Source and backup SHA-256: `3e43b7d222dd05cc191847c1991eb3972669c206d4f534ec3f4c95ca1d915a01`.
- Six registrations migrated: four TABLEs and two semantic VIEWs.
- All four TABLEs matched metadata location, table UUID, current snapshot, schema, partition spec, sort order, and snapshot history count.
- No Iceberg data files or metadata files were rewritten during migration.
- No snapshots advanced during migration; later snapshot advances came from normal legacy medallion cycles after the backend was active.
- Active runtime remains `SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`.

## Verification

- `dbt test`: `PASS=26 WARN=0 ERROR=0 TOTAL=26`.
- Targeted regression: `10 passed, 7 deselected`.
- Ruff: passed.
- Compose config and `validate_runtime_config.py`: passed.
- Concurrent writer/medallion/Trino/dbt proof: no `SQLITE_BUSY`, database locking failure, `UncheckedSQLException`, lost catalog update, or metadata pointer divergence.
- Medallion completed successful legacy cycles with `work_in_flight=0`, `shadow_mismatches=0`, and `ff14_conflicts=0`.

## Deviation

Two HTTP 409 `AlreadyExistsException` responses occurred during idempotent startup namespace creation for existing `silver` and `gold` namespaces. They were not database lock failures; successful medallion cycles followed. This remains a small runtime initialization-noise issue, not a catalog migration blocker.

## Recovery

Rollback is fail-closed: stop writer/medallion/Trino, restore the SQLite `CATALOG_URI` and writable catalog volume configuration, recreate REST, verify the frozen inventory, then restart clients. Kafka checkpoints were not touched.

## Next

Ready for 01-02B only after review of this summary. Do not start 01-02C, 01-03, or later plans from this checkpoint.

## Self-Check: PASSED
