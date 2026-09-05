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

## Development workflow

`openspec/specs/development-workflow/spec.md` is the canonical integration
contract. `main` is the sole permanent development and integration branch.

For every governed change:

- Create the implementation branch from the current `main`.
- Do not create a new change from another working, integration, test, staging,
  release, or already-merged feature branch.
- One branch carries one bounded OpenSpec change or one independently
  releasable fix.
- Normal pull requests target `main`.
- A pull request represents proposed integration. Do not open one only to
  obtain a CI execution context; use `workflow_dispatch` through
  `ci-capability-dispatch.yml` with the exact SHA instead.
- Keep divergence from `main` small. Beyond three calendar days is a warning
  and beyond seven requires a recorded rationale, but elapsed time is only the
  visible symptom — conceptual divergence is the governing invariant, and a
  branch that no longer reviews as one change is decomposed regardless of age.
- After a branch has integrated, do not continue governed work on it.
  Successor work — including adoption, archival and closure of the same
  change — starts again from the current `main`.
- Integrated branches are deleted. Anchor evidence to immutable identity —
  commit SHA, workflow run id, artifact digest, pull request number, archived
  OpenSpec change — rather than to a branch continuing to exist.
- Do not use environment branches (`dev`, `test`, `staging`, `prod`) or
  permanent integration lanes.

Before starting implementation, verify the current branch's ancestry against
`main`. If the working branch did not originate from an appropriate current
`main` baseline, stop and re-derive the work onto a compliant branch rather
than extending the stale baseline.

Recorded exceptions are defined only in the **Recorded exceptions** table of
`openspec/specs/development-workflow/spec.md`. Do not infer a new exception
from existing branch topology: an existing worktree or branch is not evidence
that it is a valid base for new work.

### Branch and worktree closure

Cleanup is part of the Definition of Done. A change is not closed merely
because implementation, verification, adoption or integration passed.

After the change has integrated into `main` and its receipts are recorded:

- Verify the final implementation commit is an ancestor of `main`.
- Close any pull request that was opened only for validation or integration.
- Remove the dedicated worktree for the completed change.
- Delete the local feature, closure and integration branches for that work.
- Delete the remote branch by default. Where a long-lived historical pointer is
  genuinely needed, prefer an immutable tag over a branch that reads as active.
- Record any deliberately retained branch as an explicit exception, with its
  reason and the condition that ends it.

Never remove or force-clean a dirty worktree. Inspect and classify every
uncommitted change first, then commit, move, preserve or explicitly discard it.
Leave unrelated dirty worktrees untouched.

Do not start the next authorised item until closure cleanup for the completed
item is done, unless the exception is recorded. The handoff report states the
branch and worktree cleanup status.

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
the standing capabilities. Three of them govern how work happens and are read
together:

- `engineering-governance` — how work is authorised and fenced.
- `development-workflow` — how authorised work branches and integrates.
- `verification-contract` — what counts as verified, alongside the canonical
  commands in this file.

The remaining specs under `openspec/specs/` describe platform capabilities
rather than process; enumerate the directory rather than trusting a list here
to stay current. `openspec/changes/` holds proposals in flight.

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

[`docs/PARKED-STATE.md`](docs/PARKED-STATE.md) records the state this
repository was deliberately left in, what was closed, and every item that was
knowingly left undone with its reason. Read it before starting work; it is the
one place a deferred obligation is recorded rather than buried in an archived
task checklist.

`README.md` and the relevant files under `docs/` are the project contract for
setup, architecture, configuration, deployment, and testing. Keep them aligned
with behavior changes. Generated audit reports and analysis artifacts are
evidence and references; they do not override the repository's runtime,
development, or documentation contracts.
