# Phase 3: Staging Source Freshness Gate - Context

**Gathered:** 2026-08-17
**Status:** Ready for planning
**Source:** PRD Express Path (`docs/superpowers/specs/2026-08-17-warehouse-source-freshness-design.md`)

<domain>
## Phase Boundary

Make staging load-recency an explicit, fail-closed prerequisite to mart
certification in the batch Olist warehouse path.

**In scope:** a `loaded_at` column on the four `stg.*` tables, dbt source
freshness configuration, a distinct freshness task in
`warehouse_marts_validation` before the Cosmos dbt build, tests, and the W1/W2
documentation updates that describe the implemented state.

**Out of scope:** freshness on `core.*`; a nightly or standalone freshness job;
any change to the existing exact-parity staging gate, to `dbt build`, to the
mutation gate, or to any existing test's meaning; `loaded_at_query`; a new
audit table; missing-batch detection.

**The guarantee, stated exactly:**

> Prevent downstream certification from consuming staging whose most recent
> successful load is outside the permitted age.

This is **not** an external arrival SLA and **not** missing-batch detection.
The timestamp is written by the staging load itself and the marts DAG is
Asset-triggered by the same pipeline, so if ingestion never runs the gate never
evaluates. Plans must not widen this claim in code, comments, tests, or docs.

</domain>

<decisions>
## Implementation Decisions

Every item below is a **locked decision** from the approved spec and the
operator's implementation brief. Do not redesign unless implementation proves a
decision impossible — in that case stop and report rather than substituting an
alternative.

### Arrival signal

- Add `loaded_at timestamptz NOT NULL DEFAULT now()` to all four `stg.*`
  tables: `orders`, `order_items`, `order_payments`, `customers`.
- Deliver as a new idempotent migration `db/init/008_stg_loaded_at.sql`, using
  the `alter table if exists` / `add column if not exists` style of
  `db/init/007_pipeline_runs_ingestion_provenance.sql`.
- `loaded_at` must stay **out of** the CSV files and **out of** the `COPY`
  column lists in `dags/warehouse_orders.py`, so PostgreSQL supplies the value.
- Preserve the existing single transaction covering truncate + all four `COPY`
  operations. `now()` is transaction-start time, so one batch yields one
  identical timestamp across all four tables. This is a **batch-load
  transaction timestamp**, not literal row-arrival time.
- `clock_timestamp()` is wrong here and must not be substituted.
- `db/init/` only runs on an empty data directory, so the migration must also
  be added to the replay path in `scripts/bootstrap_stack.py`, following the
  existing `PIPELINE_PROVENANCE_MIGRATION` precedent.

### Migration false-fresh window

- `ADD COLUMN ... NOT NULL DEFAULT now()` assigns the evaluated default to
  existing rows, so immediately after migration old staging rows report as
  freshly loaded.
- This is **accepted, not fixed**. It is harmless because the gate is only ever
  reached after `load_raw_csv_to_stg`, which truncates those rows first.
- Do **not** add a nullable transitional column or a sentinel timestamp. The
  window is one ingestion run wide and the failure mode is a false pass.
- Keep this reasoning intact in code comments and docs.

### dbt source configuration

- `dbt/warehouse/models/sources.yml`, all four `staging` tables, under `config:`
  — `loaded_at_field: loaded_at` plus `warn_after` and `error_after`.
- Verified available in the pinned runtime: `SourceConfig` in dbt-core 1.12.2
  declares `freshness`, `loaded_at_field`, `loaded_at_query`.
- No freshness on `core.*` sources.
- No `loaded_at_query`.

### Gate placement and mechanism

- A distinct `check_source_freshness` task in `dags/warehouse_dbt.py`, wired
  `freshness_task >> dbt_group`, at the consumption boundary:
  core Asset received → source freshness → dbt build → artifact validation →
  publication.
- Use Cosmos `DbtSourceLocalOperator`, consistent with existing
  `DbtDocsOperator` usage.
- Do **not** use Cosmos Watcher's experimental source-freshness integration —
  the existing `DbtTaskGroup` semantics must not change silently.
- Gate on the command's exit code. Do **not** add a `sources.json` parsing
  fallback unless a test against pinned dbt-core 1.12.2 proves the CLI exit
  behaviour unsuitable.
- Reuse existing constants: `DBT_PROJECT_PATH`, `DBT_PROFILE_PATH`,
  `DBT_EXECUTABLE`, `DBT_ENV`, `_profile_config()`.

### Thresholds

- `warn_after: 30 minutes` / `error_after: 2 hours` are **provisional starting
  values**, not settled design.
- Measure healthy ingestion→marts delay before finalising, and record the
  measured basis in W1 so the numbers are evidence-based rather than guessed.
- Context that makes this matter: the marts DAG carries
  `dagrun_timeout=timedelta(minutes=45)` and `execution_timeout=40 minutes` on
  `validate_dbt_artifacts`, so a 30-minute warn sits inside delay the pipeline
  already tolerates.
- If the live stack is unavailable to measure, say so explicitly and leave the
  thresholds flagged as unmeasured rather than implying they were validated.

### Documentation

- Update W1's "Not adopted, deliberately: dbt source freshness" paragraph in the
  **same change** that activates freshness, so docs never describe an
  intermediate architecture.
- Add a freshness row to W2's "Where each layer is exercised" table.
- W1 remains the source of truth for rationale.
- The `docs/TESTING.md` entry-point work is **already complete** (commit
  `e7e1ae4`) and must be kept separate — do not redo or restructure it.

### Process constraints

- Implement in small commits with verification after each meaningful step.
- Verify assumptions against code before editing.
- Report anything not verified rather than implying it passed.

### Claude's Discretion

- Task decomposition and commit boundaries within the constraints above.
- Exact wording of code comments, docstrings and doc prose.
- Test function names and file placement, within the existing suite layout.
- Whether the freshness task is expressed via `DbtSourceLocalOperator` directly
  or wrapped, provided the operator choice and fail-closed behaviour hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Approved design
- `docs/superpowers/specs/2026-08-17-warehouse-source-freshness-design.md` — the
  approved design; scope authority for this phase.

### Warehouse contracts
- `docs/warehouse/W1-dbt-ownership.md` — dbt ownership boundary, testing layers,
  and the freshness paragraph that must change in this phase.
- `docs/warehouse/W2-execution-contract.md` — replay/failure/recovery guarantees
  and the layer table to extend.
- `docs/warehouse/W3-mutation-gate.md` — mutation catalogue conventions.

### Code under change
- `db/init/002_stg_tables.sql` — the four staging tables.
- `db/init/007_pipeline_runs_ingestion_provenance.sql` — migration style to copy.
- `dags/warehouse_orders.py` — `_copy_csv`, `STG_LOADS`, `load_raw_csv_to_stg`
  single-transaction load.
- `dags/warehouse_dbt.py` — `DbtTaskGroup`, `validate_dbt_artifacts`,
  `publish_mart_assets`, DBT constants.
- `dbt/warehouse/models/sources.yml` — source declarations.
- `scripts/bootstrap_stack.py` — migration replay path.
- `.github/workflows/ci-pr.yml` — `warehouse-dbt-contract` job.

### Repository policy
- `AGENTS.md` — authoritative verification contract and completion gate.
- `CLAUDE.md` — dbt venv invocation rules; stateful-service boundary.

</canonical_refs>

<specifics>
## Specific Ideas

### Required tests

- fresh staging → freshness passes;
- deliberately stale staging beyond the error threshold → freshness fails and
  blocks dbt build and mart publication;
- all four staging tables receive the **same** transaction timestamp;
- existing staging row-count validation remains intact;
- existing core/mart publication fail-closed behaviour remains intact;
- the migration/bootstrap path applies the new migration;
- static DAG/dbt contract tests updated as needed.

The stale test must be deterministic — backdate with
`update stg.orders set loaded_at = now() - interval '3 hours'`, never a sleep.
Existing fixture tests must not become time-dependent.

### Required verification

targeted pytest; `dbt source freshness` on pinned dbt-core 1.12.2; dbt
unit/data tests; `dbt build` on an isolated/test warehouse; sqlfluff; the
relevant Airflow BDD scenarios; the mutation gate if the live stack is
available.

**Stateful boundary:** verify the live `dwh` database is untouched unless
explicitly running the approved isolated/live-stack verification.

### Definition of done

freshness is an explicit fail-closed prerequisite to mart certification; the
feature guarantee matches the approved spec exactly; thresholds are
evidence-based; docs describe the implemented state; all relevant tests pass;
anything unverified is reported rather than implied.

</specifics>

<deferred>
## Deferred Ideas

- An Airflow Param escape hatch allowing a deliberate re-run to bypass the gate.
  Discussed and explicitly excluded; revisit only if the operational cost of a
  blocked manual marts re-trigger proves real.
- True missing-batch detection via an independent expected-arrival schedule or
  upstream arrival signal.
- Model freshness (as distinct from source freshness).

</deferred>

---

*Phase: 03-staging-source-freshness-gate*
*Context gathered: 2026-08-17 via PRD Express Path*
