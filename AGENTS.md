# DE Practicum — repository instructions

## Scope

This repository is a local Docker Compose data-engineering platform. Keep
changes specific to this project; do not import instructions or workflows from
other repositories.

## Architecture

- Airflow orchestrates scheduled pipelines and maintenance DAGs.
- Spark 4.2 handles batch/stream processing and writes raw Parquet to the
  MinIO landing area.
- The PyIceberg writer ingests landing files into the Iceberg REST catalog and
  `bronze.orders`.
- The medallion job derives `silver.orders_clean` and
  `gold.orders_daily_metrics` from Bronze.
- Trino queries Iceberg tables and runs maintenance procedures; PostgreSQL
  stores relational metadata and operational metrics.
- Kafka is the streaming input boundary. Preserve offset, checkpoint,
  idempotency, and replay/recovery semantics when changing streaming code.

The landing, Bronze, Silver, and Gold layers have different contracts. Do not
silently change schemas, deduplication rules, snapshot behavior, or ownership
of a layer without updating the relevant documentation and tests.

## Runtime safety

- Treat Docker, Kafka, Spark, MinIO, PostgreSQL, and Iceberg as stateful
  systems.
- Read-only analysis must not start/stop services, roll checkpoints, publish
  Kafka records, or mutate Iceberg tables.
- Use `stack.ps1 reset` only when explicitly requested; it removes persisted
  local Docker volumes and data.
- Keep secrets in `.env`/environment variables. Never hard-code credentials or
  commit local runtime state.
- For recovery or cutover work, identify the owner of each state transition
  and verify the checkpoint/offset/snapshot evidence before proceeding.

## Local runtime availability

Docker Desktop is installed on the local Windows development host. It may be
stopped between sessions.

**A stopped Docker daemon does NOT mean that Docker-dependent verification is
unavailable.** When an authorised change requires a live stack, start Docker
Desktop, wait for the engine to become ready, start the minimum required
services, collect the evidence, and stop any temporary capability profile when
finished.

Do not skip an applicable local integration, E2E or runtime test merely because
Docker was initially stopped. If a report says a live check could not run, it
must name what actually prevented it — not that the daemon was idle.

`docker --version` reports only the CLI. The engine is a separate question:

```bash
docker info --format '{{.ServerVersion}}'      # engine readiness
uv run python scripts/local_runtime_inventory.py
```

GitHub Actions clean-stack runs are independent reproducibility evidence and do
not substitute for an available local runtime. Local first, then CI.

`docs/LOCAL-ENVIRONMENT.md` holds the full execution contract, the startup
procedure and the last measured snapshot of this machine.

## Development and tests

- Use the documented Compose files and commands in `README.md` and `docs/`.
- Start the local stack with `stack.ps1 up` (or the documented Compose
  equivalent), and inspect it with `stack.ps1 status` and `stack.ps1 logs`.
- Run Python tools through the locked project environment with
  `uv run --locked`. `pytest.ini` excludes tests requiring the live stack; use
  the explicit `integration`, `iceberg`, `trino`, `e2e`, `airflow`, or `bdd`
  markers when their dependencies are available — and see **Local runtime
  availability** below for what "available" means, because a stopped Docker
  Desktop is available.
- When changing a pipeline or schema, update focused tests and the applicable
  documentation. Prefer deterministic, idempotent tests over live-state tests
  unless a live integration is the requirement being verified.

## Verification contract

This section is the canonical repository policy for deciding when a change is
verified. The completion gate below must pass before a change is handed off.

During iteration, use the narrowest relevant check. Run the completion gate
only when the implementation is ready.

Before completing any non-documentation Python change, run:

```bash
uv run --locked ruff check .
uv run --locked black --check .
uv run --locked mypy
uv run --locked pytest
```

`mypy` checks the typed scope declared in `pyproject.toml` — currently
`iceberg/`. Ruff is a linter and not a type checker, so the two are
complementary and neither substitutes for the other. The typed scope expands
monotonically: new first-party modules join it by default, and a module already
in scope is never removed to make CI green. Suppressions carry their narrow error
code and a reason; `warn_unused_ignores` turns a suppression that stops being
needed into an error.

The existing CI workflow also defines this coverage check:

```bash
uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90
```

That command previously had a known baseline gap and exited with status 1. It no
longer does: coverage remediation landed as its own task and total `iceberg`
coverage is 93.66% with 292 passing fast tests, so the check is now a passing
completion gate and any failure is a real regression. Do not lower the
threshold, omit modules from `--cov=iceberg`, or add filler tests to clear it;
new production code in `iceberg/` lands with dependency-free unit coverage.

Run additional checks according to the changed surface:

- DAG changes: `uv run --locked ruff check dags --select AIR3 --preview`.
- Compose or runtime configuration changes:
  `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml --profile '*' config --quiet`.
- Airflow runtime changes: run
  `uv run --locked pytest tests/test_h1_runtime.py`, validate DAG imports with
  `uv run --locked pytest tests/test_dags.py -m airflow`, execute the Gherkin
  behavior contract with
  `uv run --locked pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"`,
  and perform a short scheduler, triggerer, and DAG-processor health smoke.
- `dbt/warehouse` model or source changes: regenerate the manifest
  (`dbt parse` after deleting `target/manifest.json`), run the pinned dbt Doctor
  architecture gate, and run `uv run --locked pytest tests/test_warehouse_dbt.py`.
  Run `dbt build` as well when model SQL changed and the stack is available. The
  commands are in [docs/TESTING.md](docs/TESTING.md#warehouse-dbt); the gate and
  its accepted exceptions are in
  [docs/warehouse/W4-dbt-architecture-gate.md](docs/warehouse/W4-dbt-architecture-gate.md).
- Dependency input changes: regenerate the existing committed lock files with
  the repository lock script and verify the resulting diff.
- Streaming, schema, recovery, or other stateful changes: run the relevant
  integration or E2E gate when its live dependencies are available and the task
  authorizes state mutation. Docker Desktop being stopped does not make them
  unavailable; start it.

Documentation-only changes do not require the Python completion gate unless
they change executable commands or configuration examples.

When handing off a change, report the exact checks that ran and any live checks
that were skipped. Do not claim a check passed unless it was executed.

Do not add a test framework, task runner, wrapper script, or verification layer
unless the requested change explicitly requires it.

## Provenance and identity

`docs/PROVENANCE.md` is the platform's identity contract: which identifier is
authoritative for which concern, how cross-references are recorded, and why
identifiers are linked rather than merged. Its executable half is
`iceberg/common/provenance.py`.

Two rules bind new code. A provenance envelope never fabricates an identifier it
does not have — absence is recorded with a reason. And high-cardinality identity
(`trace_id`, `run_id`, `cycle_id`, `load_id`, Kafka offsets, snapshot ids,
business keys) never becomes a Prometheus label; a test parses every metric
declaration and fails on one.

## Runtime lineage

`docs/LINEAGE.md` records what this repository can answer about where a row came
from, and its OpenLineage section is the contract for emitted lineage. The
executable half is `iceberg/common/lineage.py`.

Three rules bind new code that emits lineage. An edge belongs only to the
boundary that actually performed it — a relationship that is merely derivable is
a documented gap, never an emitted edge. One output dataset has one owning job,
enforced by `register_edge_owner()` at service startup. And emission is
fail-open: it is wrapped, counted and never allowed to fail the data path, which
is the one place this repository deliberately does not fail closed.

Dataset names come from configured endpoints, never from a hostname or container
id. Adding an identifier to a lineage facet means adding it to
`provenance.CANONICAL_FIELDS` and `docs/PROVENANCE.md` together; the envelope
refuses names outside the vocabulary, and that friction is deliberate.

## Planning methodology

Work is planned as OpenSpec changes under `openspec/`. `openspec/specs/` holds
the standing capabilities — `engineering-governance` (how work is authorised and
fenced) and `verification-contract` (what counts as verified, alongside the
canonical commands in this file). `openspec/changes/` holds proposals in flight.

`openspec/backlog/` holds work that is specified but **not authorised** — see
`openspec/backlog/README.md`. A backlog item is not an authorisation to execute
and not evidence of current behaviour; starting one means opening the OpenSpec
change its index row names, which requires its own explicit authorisation. The
current backlog is the NG-0.1 … NG-2.2 next-generation platform package under
`openspec/backlog/next-generation/`.

GSD execution is frozen as of 2026-08-18. `.planning/` stays tracked as the
historical execution record of Phases 1-4 and must not be resumed as a work
queue; obligations that were never executed are listed with their OpenSpec
successors in `.planning/STATE.md`. Do not create new `.planning/phases/*` plans
and do not run GSD phase orchestration.

## Documentation

`README.md` and the relevant files under `docs/` are the project contract for
setup, architecture, configuration, deployment, and testing. Keep them aligned
with behavior changes. Generated audit reports and analysis artifacts are
evidence and references; they do not override the repository's runtime,
development, or documentation contracts.
