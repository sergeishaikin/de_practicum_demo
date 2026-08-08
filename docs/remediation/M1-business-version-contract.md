# M1 — executable `business_version` contract

Status: **complete**.

## Contract

`business_version` is domain ordering. Kafka partition and offset remain transport metadata and
are only a deterministic tie-breaker when the domain version is unavailable or equal.

The field now exists in:

- producer JSON events;
- Spark `ORDER_SCHEMA` and the PostgreSQL streaming sink;
- Bronze Iceberg `TABLE_SCHEMA`;
- full-overwrite Silver `SILVER_SCHEMA` and resolver;
- unit, contract, SPIKE-2 and E2E fixtures.

Existing Bronze and Silver tables receive the field through additive optional schema evolution. The
full-overwrite medallion remains the current execution model; only its current-row comparator now
uses `business_version`.

## Gates

Unit/static validation:

```text
51 passed
py_compile: passed
ruff: passed
```

Live gate:

```text
python -m pytest -m e2e tests/e2e/test_lakehouse_e2e.py -s
1 passed in 94.32s
```

The deterministic fixture used 101 events, including:

```text
dup-1: v1 → v5 → late v3
dup-2/dup-3: v1 → v5
```

Observed chain:

```text
101 Kafka events
  → 99 non-null landing/Bronze rows
  → 95 current Silver rows
```

The E2E assertions verified that `business_version` was non-null in Landing/Bronze, that the exact
version distribution matched between the fixture, Landing and Bronze, that Bronze contained
`max(business_version)=5` for `dup-1`, and that full-overwrite Silver retained v5 rather than the
later transport offset carrying v3.

Equal-version/conflicting-payload coverage is defined in the contract/unit tests for the future
FF-14 enforcement path; it is not published into this clean E2E fixture because the current M1
medallion is not yet the B2 rejection boundary.

## Handoff

M1 is the checkpoint for M2. The next milestone is the Landing-to-Bronze commit/progress boundary:
replace the settle-time heuristic as the authority for committed batches, publish bounded durable
control state, and test the crash window between a successful Silver commit and progress commit.
