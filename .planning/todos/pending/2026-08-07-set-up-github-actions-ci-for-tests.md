---
created: 2026-08-07T18:08:39.341Z
title: Set up GitHub Actions CI for tests
area: tooling
priority: 5
files:
  - .github/workflows/
  - tests/
  - docker-compose.yml
---

## Problem

There is no CI. The review scores CI/CD testing 3/10. Test runs are local-only: `pytest` for unit tests and manual `docker compose up` for the stack.

## Solution

PR workflow (gate for merge), threshold stays **90%** (not 93%):

```text
docker compose config          # compose file is valid
ruff check
black --check
pytest tests -m "not integration and not e2e"   # fast unit suite
coverage >= 90
pytest tests -m airflow        # DAG tests (separate job/container)
```

Nightly workflow: `docker compose up -d`, run the integration layer (`pytest tests/integration -m integration`) and the full E2E (`pytest tests -m e2e`), post results (to a scheduled issue / job summary).

Wiring for local runs goes through `stack.ps1`:

```powershell
.\stack.ps1 test              # fast unit suite
.\stack.ps1 test-integration  # compose stack + integration layer
.\stack.ps1 test-e2e          # full streaming E2E
```
