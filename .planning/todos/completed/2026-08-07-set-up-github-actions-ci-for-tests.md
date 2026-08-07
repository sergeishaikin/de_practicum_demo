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

## Done (2026-08-07)

Three workflows under `.github/workflows/`:

- **`ci-pr.yml`** (PR gate + push to main): compose validation (`docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet`), `ruff check .`, `black --check .`, fast unit suite with `--cov=iceberg --cov-fail-under=90`, and Airflow DagBag validation (builds `de-demo-airflow` with buildx layer-cache, starts base stack, runs `tests/test_dags.py -m airflow`). Unit job needs no Docker.
- **`ci-integration.yml`** (manual + push to main): starts ONLY `minio iceberg-rest trino` from the extended compose (the 9 live tests create their own tables; spark/kafka not needed), creates the `de-practicum` bucket, waits for readiness, runs `tests/integration -m integration`, uploads stack logs on failure.
- **`ci-nightly.yml`** (02:15 UTC + manual): full stack `--build`, integration layer, deterministic E2E (auto-enabled when `tests/e2e/` exists), maintenance DAG end-to-end via `scripts/verify_maintenance_dag.py` (trigger + poll `marts.maintenance_runs`), log artifact upload.

Prerequisites the gate required (repo did NOT pass ruff/black before this todo):

- `requirements-dev.txt` (pinned: pytest 8.4.2, pytest-cov 7.1.0, ruff 0.12.0, black 25.9.0, pyiceberg 0.11.1, pyarrow 21.0.0, psycopg2-binary 2.9.12).
- 12 files black-reformatted; ruff fixes in `tests/test_ops.py` (unused import), `tests/test_medallion.py` (dead var), `tests/integration/test_iceberg_trino.py` (ambiguous `l`), `scripts/dump_dag_structure.py` (E402), `temp_create_superset_assets.py` (E402/F401).
- Docs corrected: `CONFIGURATION.md` now states the maintenance tables are hardcoded (not env-configurable); `TESTING.md`/`DEPLOYMENT.md` CI sections rewritten.

Verified locally: ruff/black clean, compose config RC=0, fast suite 39 passed @ 90% coverage, DagBag 8 passed, `verify_maintenance_dag.py` triggers the DAG and sees audit rows for all 3 tables.

Deliberate gaps (noted, not blocking): the `stack.ps1` wrapper is a separate pending todo (pytest-markers-and-stack-test-commands). CI can't be executed from here (needs GitHub) — workflows validated with YAML parse + the exact compose/test commands proven locally. Coverage sits exactly at 90%, so any new uncovered code must be paired with tests.
