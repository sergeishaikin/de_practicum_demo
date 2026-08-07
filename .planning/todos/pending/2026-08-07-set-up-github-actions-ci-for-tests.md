---
created: 2026-08-07T18:08:39.341Z
title: Set up GitHub Actions CI for tests
area: tooling
files:
  - .github/workflows/
  - tests/
  - docker-compose.yml
---

## Problem

There is no CI. The review scores CI/CD testing 3/10. Test runs are local-only: `pytest` for unit tests and manual `docker compose up` for the stack.

## Solution

Add GitHub Actions:
- PR workflow: `ruff`, `black --check`, `pytest` (fast unit suite), coverage report, SQL checks (`docker compose config` / lint the DDL).
- Nightly workflow: `docker compose up -d`, run integration layer (Iceberg/Trino), Spark E2E, and the maintenance DAG; post results back to the PR or a scheduled issue.
- Gate merges on the PR workflow passing and coverage not dropping below the target.
