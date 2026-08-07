---
created: 2026-08-07T18:08:39.341Z
title: Add pytest markers and stack test commands
area: tooling
priority: infra (prerequisite for priority 3 and 5)
files:
  - pytest.ini
  - stack.ps1
---

## Problem

The integration and E2E suites need to be selectable so the fast unit suite stays Docker-free, and the stack wrapper needs first-class test commands. Nothing exists yet.

## Solution

Add markers (in `pytest.ini` or a `[tool.pytest.ini_options]` section):

```ini
[pytest]
markers =
    integration: requires local Compose stack (real MinIO/REST catalog/Trino)
    e2e: full Kafka/Spark/lakehouse test
    airflow: Airflow DAG validation
```

Standard commands:

```powershell
pytest tests -m "not integration and not e2e"     # fast unit suite
pytest tests/integration -m integration            # integration layer
pytest tests -m e2e                                # nightly E2E
pytest tests -m airflow                            # DAG tests
```

Add `stack.ps1` subcommands:

```powershell
.\stack.ps1 test
.\stack.ps1 test-integration
.\stack.ps1 test-e2e
```

Prevents accidental live-stack test runs in the fast suite.
