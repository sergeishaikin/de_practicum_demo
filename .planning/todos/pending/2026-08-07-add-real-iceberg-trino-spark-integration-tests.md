---
created: 2026-08-07T18:08:39.341Z
title: Add real Iceberg Trino Spark integration tests
area: testing
files:
  - tests/
  - docker-compose.yml
---

## Problem

The unit suite mocks the catalog, S3, and Postgres entirely. The review scores integration automation 6.5/10: no automated tests run against the real MinIO + REST catalog + Iceberg tables, no Trino SQL checks, and no Spark→Kafka→landing→writer→bronze→silver→gold E2E validation. These are slower (1–3 min) but validate the lakehouse invariants that fakes cannot.

## Solution

Add a `tests/integration/` layer (opt-in via marker, run against `docker compose up`):
- `test_iceberg.py` — write/append via real catalog; verify snapshots, `load-id` metadata, dedup in silver, aggregation values in gold (deterministic, e.g. UK revenue 1250 / US 900 / total 2150).
- `test_trino_queries.py` — `SELECT` across bronze/silver/gold, `MERGE`/upsert semantics, snapshot history, time travel, and maintenance procedures (`expire_snapshots`, `optimize`, `remove_orphan_files`) SQL.
- `test_spark_e2e.py` — produce ~100 Kafka events → Spark → landing Parquet → writer → bronze → silver → gold → assert row counts and metrics rows. Nightly-only.
- Keep them behind `@pytest.mark.integration` so the fast unit suite stays Docker-free.
