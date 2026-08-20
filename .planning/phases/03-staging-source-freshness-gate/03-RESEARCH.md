# Phase 3: Staging Source Freshness Gate - Research

**Researched:** 2026-08-17
**Domain:** dbt source freshness (dbt-core 1.12.2 / dbt-postgres 1.11.0), Astronomer Cosmos 1.15.0 local operators, Airflow 3.3.1 Asset-triggered DAG wiring, PostgreSQL additive DDL migration replay
**Confidence:** HIGH for the mechanics questions (1, 2, 3, 5); HIGH for CI shape (4); MEDIUM only where a live stack would be required (threshold measurement, DagBag graph shape after wiring)

**Verdict on feasibility:** The approved design is **implementable as specified**. Nothing in this research contradicts it. Two mechanical facts materially refine *how* it must be implemented (see `## Design-Critical Findings`), but neither changes the design, the signal, the placement, or the guarantee.

**Research method note:** `astronomer-cosmos==1.15.0` is not installed in any host venv, but the **exact pinned wheel is unpacked in the local uv cache** at
`C:\Users\serge\AppData\Local\uv\cache\archive-v0\jI4EXMKtix3GjCyVDM-12\cosmos\`
(`astronomer_cosmos-1.15.0.dist-info/METADATA` reports `Name: astronomer-cosmos` / `Version: 1.15.0`). Every Cosmos claim below is read directly from that source tree — this is the same artifact the Airflow image installs, so these findings are **VERIFIED against the pinned package**, not against documentation. dbt claims are read from `.venv-dbt-warehouse/Lib/site-packages/dbt/` (`dbt_core-1.12.2.dist-info`, `dbt_postgres-1.11.0.dist-info`).

**No services were started. No dbt command was executed. No database was touched.** All findings are static source inspection.

---

<user_constraints>
## User Constraints (from 03-CONTEXT.md)

### Locked Decisions

**Arrival signal**
- Add `loaded_at timestamptz NOT NULL DEFAULT now()` to all four `stg.*` tables: `orders`, `order_items`, `order_payments`, `customers`.
- Deliver as a new idempotent migration `db/init/008_stg_loaded_at.sql`, using the `alter table if exists` / `add column if not exists` style of `db/init/007_pipeline_runs_ingestion_provenance.sql`.
- `loaded_at` must stay **out of** the CSV files and **out of** the `COPY` column lists in `dags/warehouse_orders.py`, so PostgreSQL supplies the value.
- Preserve the existing single transaction covering truncate + all four `COPY` operations. `now()` is transaction-start time, so one batch yields one identical timestamp across all four tables. This is a **batch-load transaction timestamp**, not literal row-arrival time.
- `clock_timestamp()` is wrong here and must not be substituted.
- `db/init/` only runs on an empty data directory, so the migration must also be added to the replay path in `scripts/bootstrap_stack.py`, following the existing `PIPELINE_PROVENANCE_MIGRATION` precedent.

**Migration false-fresh window**
- `ADD COLUMN ... NOT NULL DEFAULT now()` assigns the evaluated default to existing rows, so immediately after migration old staging rows report as freshly loaded.
- This is **accepted, not fixed**. It is harmless because the gate is only ever reached after `load_raw_csv_to_stg`, which truncates those rows first.
- Do **not** add a nullable transitional column or a sentinel timestamp. The window is one ingestion run wide and the failure mode is a false pass.
- Keep this reasoning intact in code comments and docs.

**dbt source configuration**
- `dbt/warehouse/models/sources.yml`, all four `staging` tables, under `config:` — `loaded_at_field: loaded_at` plus `warn_after` and `error_after`.
- Verified available in the pinned runtime: `SourceConfig` in dbt-core 1.12.2 declares `freshness`, `loaded_at_field`, `loaded_at_query`.
- No freshness on `core.*` sources.
- No `loaded_at_query`.

**Gate placement and mechanism**
- A distinct `check_source_freshness` task in `dags/warehouse_dbt.py`, wired `freshness_task >> dbt_group`, at the consumption boundary: core Asset received → source freshness → dbt build → artifact validation → publication.
- Use Cosmos `DbtSourceLocalOperator`, consistent with existing `DbtDocsOperator` usage.
- Do **not** use Cosmos Watcher's experimental source-freshness integration — the existing `DbtTaskGroup` semantics must not change silently.
- Gate on the command's exit code. Do **not** add a `sources.json` parsing fallback unless a test against pinned dbt-core 1.12.2 proves the CLI exit behaviour unsuitable.
- Reuse existing constants: `DBT_PROJECT_PATH`, `DBT_PROFILE_PATH`, `DBT_EXECUTABLE`, `DBT_ENV`, `_profile_config()`.

**Thresholds**
- `warn_after: 30 minutes` / `error_after: 2 hours` are **provisional starting values**, not settled design.
- Measure healthy ingestion→marts delay before finalising, and record the measured basis in W1 so the numbers are evidence-based rather than guessed.
- Context that makes this matter: the marts DAG carries `dagrun_timeout=timedelta(minutes=45)` and `execution_timeout=40 minutes` on `validate_dbt_artifacts`, so a 30-minute warn sits inside delay the pipeline already tolerates.
- If the live stack is unavailable to measure, say so explicitly and leave the thresholds flagged as unmeasured rather than implying they were validated.

**Documentation**
- Update W1's "Not adopted, deliberately: dbt source freshness" paragraph in the **same change** that activates freshness, so docs never describe an intermediate architecture.
- Add a freshness row to W2's "Where each layer is exercised" table.
- W1 remains the source of truth for rationale.
- The `docs/TESTING.md` entry-point work is **already complete** (commit `e7e1ae4`) and must be kept separate — do not redo or restructure it.

**Process constraints**
- Implement in small commits with verification after each meaningful step.
- Verify assumptions against code before editing.
- Report anything not verified rather than implying it passed.

### Claude's Discretion

- Task decomposition and commit boundaries within the constraints above.
- Exact wording of code comments, docstrings and doc prose.
- Test function names and file placement, within the existing suite layout.
- Whether the freshness task is expressed via `DbtSourceLocalOperator` directly or wrapped, provided the operator choice and fail-closed behaviour hold.

### Deferred Ideas (OUT OF SCOPE)

- An Airflow Param escape hatch allowing a deliberate re-run to bypass the gate. Discussed and explicitly excluded; revisit only if the operational cost of a blocked manual marts re-trigger proves real.
- True missing-batch detection via an independent expected-arrival schedule or upstream arrival signal.
- Model freshness (as distinct from source freshness).
</user_constraints>

---

## Design-Critical Findings

Two facts that the planner **must** encode into the plan. Neither changes the design; both change the code that implements it.

### DCF-1 — `DbtSourceLocalOperator` is not re-exported; the import path is `cosmos.operators.local`

**VERIFIED.** `cosmos/operators/__init__.py` (full file, 27 lines) re-exports twelve `*LocalOperator` classes under short aliases. `DbtSourceLocalOperator` is **not among them**:

```
from .local import DbtBuildLocalOperator as DbtBuildOperator
... DbtDepsOperator, DbtDocsAzureStorageOperator, DbtDocsGCSOperator,
    DbtDocsOperator, DbtDocsS3Operator, DbtLSOperator, DbtRunOperator,
    DbtRunOperationOperator, DbtSeedOperator, DbtSnapshotOperator, DbtTestOperator
__all__ = [12 names, none of them a Source operator]
```

`cosmos/__init__.py`'s lazy-import map (`_LAZY_IMPORTS`, lines 36–44 and the `TYPE_CHECKING` block at 230–238) lists nine `cosmos.operators.local` classes, again with no Source operator. The only `DbtSource*` name at the top level is `DbtSourceAwsEcsOperator` (`cosmos/__init__.py:89`, `:139`).

The class itself is defined at **`cosmos/operators/local.py:1181`**:

```python
class DbtSourceLocalOperator(DbtSourceMixin, DbtLocalBaseOperator):
```

**Consequence for the plan:** the existing DAG line
`from cosmos.operators import DbtDocsOperator`
**cannot** be extended to `from cosmos.operators import DbtDocsOperator, DbtSourceLocalOperator` — that raises `ImportError` and would break the whole DagBag. The correct import is:

```python
from cosmos.operators.local import DbtSourceLocalOperator
```

Verified sibling classes exist at the same path, so a mixed import is also possible:
`from cosmos.operators.local import DbtDocsLocalOperator, DbtSourceLocalOperator` — but changing the existing `DbtDocsOperator` import is unnecessary churn.

### DCF-2 — In the Airflow image, Cosmos uses **`InvocationMode.DBT_RUNNER`, not subprocess**

**VERIFIED.** Three facts compose:

1. `airflow.requirements.in` pins `dbt-core==1.12.2`, `dbt-postgres==1.11.0`, `dbt-trino==1.10.3` **into the Airflow image's own Python environment** (lines 4–6; corresponding hash-pinned entries at `airflow.requirements.txt:445`, `:473`, `:484`).
2. `cosmos/dbt/runner.py:29–36`:
   ```python
   @cache
   def is_available() -> bool:
       try:
           from dbt.cli.main import dbtRunner  # noqa
       except ImportError:
           return False
       return True
   ```
3. `cosmos/operators/local.py:287–296` `_discover_invocation_mode()` — called from `run_command` when `self.invocation_mode` is falsy (`local.py:688-689`):
   ```python
   if dbt_runner.is_available():
       self.invocation_mode = InvocationMode.DBT_RUNNER
   else:
       self.invocation_mode = InvocationMode.SUBPROCESS
   ```

So inside `de-demo-airflow`, dbt runs **in-process via `dbtRunner`**, and:

- `dbt_executable_path` is **ignored** (`cosmos/dbt/runner.py:93` — `cli_args = command[1:]` explicitly discards the executable that `build_cmd` prepended at `cosmos/operators/base.py:292`). Passing `dbt_executable_path=DBT_EXECUTABLE` is harmless and consistent with the existing `DbtDocsOperator`, but it is **not** what makes dbt run.
- Failure is signalled by `dbtRunnerResult.success is False`, handled at `cosmos/operators/local.py:306-308` → `cosmos/dbt/runner.py:145-156` `handle_exception_if_needed`, which raises `CosmosDbtRunError`.

**This does not weaken the gate.** dbt's own CLI exit code and `dbtRunnerResult.success` are derived from *the same boolean*. Verified in `dbt/cli/main.py`:

```python
# dbt/cli/main.py:816-829  (the `dbt source freshness` command body)
results = task.run()
success = task.interpret_results(results)
return results, success
```

`dbt/cli/requires.py:258-259` (`postflight`): `if not success: raise ResultExit(result)`.
`dbt/cli/exceptions.py`: `ResultExit.__init__` → `super().__init__(ExitCodes.ModelError)`; `ExitCodes.ModelError = 1` (`dbt/utils/utils.py:43-46`).
`dbt/cli/main.py:80-84` (the `dbtRunner.invoke` wrapper): `except requires.ResultExit as e: return dbtRunnerResult(result=e.result, success=False)`.

So: **error-level freshness → `success=False` → exit code 1 on the CLI *and* `CosmosDbtRunError` under `dbtRunner`.** Identical semantics, two surfaces. The CI step (question 4) exercises the CLI surface; the Airflow task exercises the runner surface; both are gated by the same `interpret_results` computation. That is worth one sentence in W1 so the next reader doesn't think the CI proof and the runtime path diverge.

**Consequence for the plan:** the design's phrase "gate on the command's exit code" is satisfied, but the *phrasing in code comments and docs* should say "gate on the dbt result status (exit code on the CLI, `dbtRunnerResult.success` under Cosmos's in-process runner)" rather than implying a subprocess.

---

## Q1 — Cosmos `DbtSourceLocalOperator` (astronomer-cosmos 1.15.0)

All **VERIFIED** by reading the pinned wheel in the uv cache.

### Import path

```python
from cosmos.operators.local import DbtSourceLocalOperator   # cosmos/operators/local.py:1181
```

See **DCF-1** — no shorter path exists.

### Class definition (verbatim, `cosmos/operators/local.py:1181-1219`)

```python
class DbtSourceLocalOperator(DbtSourceMixin, DbtLocalBaseOperator):
    """
    Executes a dbt source freshness command.
    """

    template_fields: Sequence[str] = DbtLocalBaseOperator.template_fields

    def __init__(self, *args: Any, on_warning_callback: Callable[..., Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.on_warning_callback = on_warning_callback
        self.extract_issues: Callable[..., tuple[list[str], list[str]]]

    def _handle_warnings(self, result, context) -> None:
        if self.invocation_mode == InvocationMode.SUBPROCESS:
            self.extract_issues = extract_freshness_warn_msg
        elif self.invocation_mode == InvocationMode.DBT_RUNNER:
            self.extract_issues = dbt_runner.extract_message_by_status
        test_names, test_results = self.extract_issues(result)
        warning_context = dict(context)
        warning_context["test_names"] = test_names
        warning_context["test_results"] = test_results
        self.on_warning_callback and self.on_warning_callback(warning_context)

    def execute(self, context: Context, **kwargs: Any) -> None:
        result = self.build_and_run_cmd(context=context, cmd_flags=self.add_cmd_flags())
        if self.on_warning_callback:
            self._handle_warnings(result, context)
```

The command it runs is fixed by the mixin (`cosmos/operators/base.py:433-439`):

```python
class DbtSourceMixin:
    """Executes a dbt source freshness command."""
    base_cmd = ["source", "freshness"]
    ui_color = "#34CCEB"
```

`add_cmd_flags()` is not overridden by `DbtSourceMixin`, so it resolves to `AbstractDbtBase.add_cmd_flags` → `return []` (`cosmos/operators/base.py:283-285`). No command-specific flags.

### Accepted constructor parameters

The MRO is `DbtSourceLocalOperator → DbtSourceMixin → DbtLocalBaseOperator → AbstractDbtLocalBase → AbstractDbtBase → BaseOperator`. Every parameter asked about is accepted:

| Parameter | Accepted | Where declared | Notes |
|---|---|---|---|
| `task_id` | ✅ | `AbstractDbtLocalBase.__init__` (`local.py:205`) — positional-first, also forwarded to `BaseOperator` | required |
| `project_dir` | ✅ | `AbstractDbtBase.__init__` (`base.py:110`) | required, `str` |
| `profile_config` | ✅ | `AbstractDbtLocalBase.__init__` (`local.py:206`) | required, `ProfileConfig` |
| `dbt_executable_path` | ✅ | `AbstractDbtBase.__init__` (`base.py:132`), default `get_system_dbt()` | **ignored under `DBT_RUNNER`** — see DCF-2 |
| `env` | ✅ | `AbstractDbtBase.__init__` (`base.py:126`), `dict[str, Any] \| None` | also a `template_field` (`base.py:91`) |
| `on_warning_callback` | ✅ | `DbtSourceLocalOperator.__init__` (`local.py:1188`) | **not required for fail-closed behaviour** |
| `callback` | ✅ | `AbstractDbtLocalBase.__init__` (`local.py:211`) | the `_persist_dbt_artifacts`-style hook |
| `invocation_mode` | ✅ | `AbstractDbtLocalBase.__init__` (`local.py:207`), default `None` → auto-discover | |
| `install_deps` | ✅ | `local.py:208`, default `True`; auto-forced to `False` when the project has no `dependencies.yml`/`packages.yml` (`local.py:246-248`) | `dbt/warehouse` has neither, so this self-disables |
| `emit_datasets` | ✅ | `base.py:118`, default `True` | see "Options worth setting" below |
| `skip_exit_code` | ✅ | `base.py:129`, **default `99`** | see below |
| `append_env` | ✅ | `local.py:213`, default `True` for local operators | |
| `warn_error` | ✅ | `base.py:123`, default `False` | **must stay `False`** — `True` would promote warn-level freshness to an error and silently defeat the warn/error threshold split |
| `trigger_rule`, `execution_timeout`, … | ✅ | via `**kwargs` → `BaseOperator` | |

Two constructor kwargs are **rejected by design**: `compiled_sql` and `freshness` are output-only template fields (`local.py:189-201`, `_reject_output_only_template_fields`) and raise `CosmosValueError` if passed.

### How failure is signalled — fail-closed **by default**, no callback needed

**VERIFIED.** `DbtSourceLocalOperator.execute` calls `build_and_run_cmd` → `run_command`. `run_command` ends with:

```python
# cosmos/operators/local.py:739-743
self._handle_post_execution(tmp_project_dir, context, push_run_results_to_xcom)
self.handle_exception(result)
```

`handle_exception` (`local.py:279-285`) dispatches on invocation mode:

```python
# local.py:299-304  (SUBPROCESS)
def handle_exception_subprocess(self, result) -> None:
    if self.skip_exit_code is not None and result.exit_code == self.skip_exit_code:
        raise AirflowSkipException(f"dbt command returned exit code {self.skip_exit_code}. Skipping.")
    elif result.exit_code != 0:
        self.log.error("\n".join(result.full_output))
        raise AirflowException(f"dbt command failed. The command returned a non-zero exit code {result.exit_code}.")

# local.py:306-308  (DBT_RUNNER)
def handle_exception_dbt_runner(self, result) -> None:
    return dbt_runner.handle_exception_if_needed(result)   # raises CosmosDbtRunError if not result.success
```

**Answer to the question as posed: an error-level freshness result raises and fails the Airflow task by default. No `on_warning_callback` and no extra config are required to fail closed.**

`on_warning_callback` is *only* a hook for surfacing **warn**-level results, which do not fail anything. This matches the design's acceptance table ("the `warn_after` threshold is not separately asserted"). Passing it is optional; the phase does not need it.

`skip_exit_code=99` deserves a note: it means "exit code 99 → mark the task *skipped* rather than failed". dbt-core 1.12.2 only ever exits `0`, `1`, or `2` (`ExitCodes` enum, `dbt/utils/utils.py:43-46`), so 99 is unreachable and the default is inert. **Do not set `skip_exit_code=None`** thinking it hardens the gate — it changes nothing here and adds an unexplained parameter.

### Options worth setting (discretionary, with reasons)

- `emit_datasets=False` — default is `True` (`base.py:118`), which makes `run_command` call `_handle_datasets(context)` (`local.py:591-600`) → `register_dataset(...)`. For a freshness run there are no OpenLineage events, so the lists are empty and this is a no-op in practice (the existing `DbtDocsOperator` already runs with the default and works). Setting it `False` is consistent with `RenderConfig(emit_datasets=False)` on the task group and removes a code path that has no purpose here.
- **Do not** pass `callback=_persist_dbt_artifacts`. `dbt source freshness` writes `target/sources.json`, not `catalog.json`/`index.html`, and it *does* regenerate `manifest.json`. Copying that into `DBT_ARTIFACT_PATH` before `dbt build` runs is pointless at best and confusing at worst. Cosmos already exposes the freshness result: `store_freshness_json` (`local.py:422-437`) reads `target/sources.json` and puts the formatted JSON into the `freshness` rendered-template field, which renders as JSON in the Airflow UI (`template_fields_renderers = {"freshness": "json"}`, `local.py:184-187`). That is free observability with no code.
- `install_deps` — leave at the default. `_has_dependencies_file` (`local.py:245`) probes the project at parse time and forces it `False`, because `dbt/warehouse` carries no `packages.yml`. The `DbtTaskGroup` passes `install_deps: False` explicitly; mirroring that on the freshness task is harmless and reads consistently.

### Cosmos Watcher's freshness integration is **not** currently active — the design's premise holds

**VERIFIED**, and worth recording because it is the one place the design could have been accidentally wrong.

`cosmos/airflow/graph.py:807-809`:

```python
if render_config is not None and render_config.source_rendering_behavior != SourceRenderingBehavior.NONE:
    producer_task_args["_check_source_freshness"] = True
```

`cosmos/config.py:104` — `source_rendering_behavior: SourceRenderingBehavior = SourceRenderingBehavior.NONE` (default since Cosmos 1.6, per the docstring at `config.py:75`).

`dags/warehouse_dbt.py:423` passes `render_config=RenderConfig(emit_datasets=False)` and does **not** set `source_rendering_behavior`. Therefore `_check_source_freshness` is **not** set on the producer, the special freshness branch in `run_command` (`local.py:726-729`) is never taken, and `DbtSourceWatcherOperator` (`cosmos/operators/watcher.py:600`) is never instantiated. The `DbtTaskGroup` today runs `dbt build` only.

Adding the standalone task therefore introduces freshness without changing any existing group semantics — exactly as the design intends. **The plan must not add `source_rendering_behavior` to `RenderConfig`.**

---

## Q2 — `dbt source freshness` exit codes under dbt-core 1.12.2

All **VERIFIED** by reading `.venv-dbt-warehouse/Lib/site-packages/dbt/` (`dbt_core-1.12.2.dist-info/METADATA`: `Version: 1.12.2`; `dbt_postgres-1.11.0.dist-info`: `Version: 1.11.0`). **No dbt command was run.**

### The exit-code chain

| Step | Source | Behaviour |
|---|---|---|
| 1 | `dbt/cli/main.py:816-829` | `freshness()` runs `FreshnessTask`, then `success = task.interpret_results(results)`, returns `(results, success)` |
| 2 | `dbt/task/freshness.py:202` | `class FreshnessTask(RunTask)` — **does not override `interpret_results`** (grep across `freshness.py`, `run.py`, `runnable.py`, `base.py` finds the definition only at `runnable.py:804`) |
| 3 | `dbt/task/runnable.py:803-820` | `GraphRunnableTask.interpret_results` counts `RuntimeErr + Error + Fail + Skipped + PartialSuccess`; returns `num_total == 0` |
| 4 | `dbt/cli/requires.py:258-259` | `postflight`: `if not success: raise ResultExit(result)` |
| 5 | `dbt/cli/exceptions.py` | `ResultExit → CliException(ExitCodes.ModelError)`; `CliException.__init__` sets `self.exit_code = exit_code.value`, which click uses as the process exit code |
| 6 | `dbt/utils/utils.py:43-46` | `class ExitCodes(int, Enum): Success = 0; ModelError = 1; UnhandledError = 2` |

### Which statuses count

`dbt/artifacts/schemas/results.py:89-93`:

```python
class FreshnessStatus(StrEnum):
    Pass       = NodeStatus.Pass          # "pass"
    Warn       = NodeStatus.Warn          # "warn"
    Error      = NodeStatus.Error         # "error"
    RuntimeErr = NodeStatus.RuntimeErr    # "runtime error"
```

The freshness statuses are *literally the same string values* as `NodeStatus` (`results.py:58-68`), and both are `StrEnum`, so the `r.status == NodeStatus.Error` comparisons in `interpret_results` match across the two enum classes.

### Result — the answer

| Freshness outcome | Counted by `interpret_results`? | `success` | **CLI exit code** | Cosmos `dbtRunner` outcome |
|---|---|---|---|---|
| **Pass** | no | `True` | **0** | no exception |
| **Warn** (`warn_after` exceeded, `error_after` not) | **no** — `Warn` is absent from the counted set | `True` | **0** | no exception; only `on_warning_callback` fires, if supplied |
| **Error** (`error_after` exceeded) | **yes** (`num_errors`) | `False` | **1** | `CosmosDbtRunError` → task fails |
| **RuntimeErr** (e.g. relation missing) | **yes** (`num_runtime_errors`) | `False` | **1** | `CosmosDbtRunError` → task fails |
| Usage / unhandled exception | — | `False` | **2** (`ExceptionExit → ExitCodes.UnhandledError`) | `CosmosDbtRunError` |

**This is exactly the behaviour the design assumed.** Error-level staleness returns non-zero; warn-level does not. The `sources.json` fallback stays out.

Threshold evaluation itself is `FreshnessThreshold.status` (`dbt/artifacts/resources/v1/components.py:180-188`) — `error_after` is checked first, then `warn_after`, else `Pass`.

**Do not set `warn_error=True`** on the operator or as a dbt global flag: it would convert the advisory warn into an error and collapse the two thresholds into one. `AbstractDbtBase` defaults it to `False` (`cosmos/operators/base.py:123`) and `add_global_flags` only appends `--warn-error` when truthy (`base.py:263-265`).

### Two adjacent behaviours the plan must know

**(a) `core.*` sources are correctly excluded — no config needed.** `FreshnessSelector.node_is_match` (`dbt/task/freshness.py:193-199`) ends in `return node.has_freshness`. `SourceDefinition.has_freshness` is `bool(self.freshness)` (`dbt/contracts/graph/nodes.py:1511-1513`), and `FreshnessThreshold.__bool__` is `bool(self.warn_after) or bool(self.error_after)` (`components.py:190-191`). `SourceConfig.freshness` defaults to an *empty* `FreshnessThreshold` (`dbt/artifacts/resources/v1/source_definition.py:23`), which is falsy. So a source with no thresholds is simply not selected. `core.orders` / `core.order_items` are silently skipped — no error, no config entry required. **This confirms "No freshness on `core.*`" needs no negative declaration.**

**(b) An *empty* staging table produces an ERROR, not a pass.** `BaseAdapter._create_freshness_response` (`dbt/adapters/base/impl.py:1644-1661`):

```python
if last_modified is None:
    # Interpret missing value as "infinitely long ago"
    max_loaded_at = datetime(1, 1, 1, 0, 0, 0, tzinfo=pytz.UTC)
```

`max(loaded_at)` over an empty table is `NULL` → age ≈ 2025 years → `error_after` exceeded → status `Error` → exit 1. This is desirable (fail-closed) but it means **`dbt source freshness` must never be run against a truncated-but-not-yet-loaded staging schema** and it must not be added to the mutation gate or any step that runs before the seed. Worth one sentence in W1.

### `config:`-level placement is the correct (non-deprecated) form in 1.12.2

**VERIFIED.** `dbt/parser/sources.py:176-179` builds the `SourceDefinition` from the resolved config:

```python
loaded_at_field=config.loaded_at_field,
loaded_at_query=config.loaded_at_query,
freshness=config.freshness,
```

and the parser comment at `sources.py:426` states plainly: *"loaded_at_field and loaded_at_query are supported both at top-level (deprecated) and config-level (preferred) on sources and tables."* Freshness merging honours source-level then table-level config (`sources.py:391-417`). The `config:` block specified in the design is the current, non-warning form.

`sources.py:186-200` additionally fires a `FreshnessConfigProblem` warning if a source declares freshness with *neither* `loaded_at_field` nor `loaded_at_query` on an adapter lacking `Capability.TableLastModifiedMetadata`. Declaring `loaded_at_field` avoids that path entirely.

---

## Q3 — Test wiring

### `tests/test_warehouse_dbt.py` — the fast, DB-free repository-contract layer

**VERIFIED** (283 lines, no pytest marker, so it runs in the default `pytest` fast suite; `pytest.ini` `addopts = -m "not integration and not e2e and not airflow"`).

Established idiom — **read the file as text and assert on substrings**:

```python
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt" / "warehouse"

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")
```

- YAML is asserted as **raw text**, never parsed (`test_sources_keep_airflow_owned_boundaries_explicit:29-35` does `assert f"name: {source_name}" in sources`; `test_quality_contracts_and_selectors_are_present:70` does `assert schema.count("enforced: true") == 4`).
- DAG structure is asserted as **source text**: `test_cosmos_warehouse_dag_uses_watcher_and_explicit_publication:274-282` does `source = read("dags/warehouse_dbt.py")` then `assert "ExecutionMode.WATCHER" in source`, `assert "publish_mart_assets" in source`, …
- CI wiring is asserted the same way: `workflow = read(".github/workflows/ci-pr.yml")` then substring / `workflow.count(...) >= 2` (`:165-169`, `:201-205`).
- Cross-file consistency is asserted by reading both files (`test_generate_schema_name_keeps_the_legacy_marts_relation_names:229-264`), and that test also shows the **graceful-degradation idiom**: if `dbt/warehouse/target/manifest.json` exists, make the stronger manifest-based assertion; otherwise `return` early.
- Every test carries a docstring or inline comment saying *why the assertion is load-bearing*, not what it checks. Match that tone.

**New tests for this phase belong here**, following the design's list:

| Assertion | Idiom to copy |
|---|---|
| four staging sources declare `loaded_at_field: loaded_at` + both thresholds | `sources.count("loaded_at_field: loaded_at") == 4`, plus `warn_after` / `error_after` counts — mirror `schema.count("enforced: true") == 4` at `:70` |
| `core.*` declares no freshness | split `sources.yml` text at `"- name: core"` and assert `"loaded_at_field" not in core_block` — mirror the `by_name = {case.splitlines()[0].strip(): case for case in cases}` splitting idiom at `:115-123` |
| DAG wires `freshness_task >> dbt_group` | `dag = read("dags/warehouse_dbt.py")`; assert the import path `from cosmos.operators.local import DbtSourceLocalOperator`, the literal `>> dbt_group`, and `"check_source_freshness"` — mirror `:274-282` |
| bootstrap replays `008_stg_loaded_at.sql` | `assert "008_stg_loaded_at.sql" in read("scripts/bootstrap_stack.py")` — **but see the stronger precedent below** |
| CI runs fresh-pass and stale-fail | `workflow = read(".github/workflows/ci-pr.yml")` substring assertions — mirror `:165-169` |

**Note the existing migration-contract precedent lives elsewhere.** `tests/test_h1_runtime.py:241-256`, `test_pipeline_provenance_migration_is_additive_and_bootstrapped`, is the exact template for the 008 migration test and already reads `db/init/007_...sql` + `scripts/bootstrap_stack.py` together:

```python
def test_pipeline_provenance_migration_is_additive_and_bootstrapped() -> None:
    base = read("db/init/004_smoke_objects.sql")
    migration = read("db/init/007_pipeline_runs_ingestion_provenance.sql")
    bootstrap = read("scripts/bootstrap_stack.py")
    ...
    assert "add column if not exists ingestion_run_id varchar" in migration
    assert "007_pipeline_runs_ingestion_provenance.sql" in bootstrap
```

`tests/test_h1_runtime.py` is also unmarked (fast suite). Either home is defensible; **`test_h1_runtime.py` is the stronger match for the migration+bootstrap assertion** (it is literally the same shape of claim about the same two files), while `test_warehouse_dbt.py` is the right home for the `sources.yml` and DAG-wiring assertions. This is a Claude's-discretion call the planner should make explicitly rather than by accident.

### `tests/test_dags.py` — the live DagBag structure layer

**VERIFIED.** Marked `pytestmark = pytest.mark.airflow` (`:44`), excluded from the fast suite, run in CI by the `airflow-dags` job (`ci-pr.yml:216`).

Mechanism: a module-scoped fixture pipes `scripts/dump_dag_structure.py` into `docker exec -i de-demo-airflow python -` and parses the last JSON line (`:47-61`). No Airflow import happens on the host.

**How task dependencies are asserted.** `scripts/dump_dag_structure.py:57-60` emits, per DAG:

```python
"tasks": {tid: sorted(t.get_direct_relative_ids(upstream=True)) for tid, t in dag.task_dict.items()},
```

i.e. **task_id → sorted list of direct upstream task_ids**. Assertions then compare that mapping. Two styles are in use:

```python
# Whole-graph equality (ingestion DAG) — tests/test_dags.py:166
assert dag["tasks"] == INGESTION_UPSTREAM       # module constant at :36-42

# Per-edge equality against a subset (marts DAG) — tests/test_dags.py:204-214
tasks = dag["tasks"]
assert {"dbt_warehouse.dbt_producer_watcher", "dbt_warehouse.dbt_producer_watcher_done",
        "generate_dbt_docs", "validate_dbt_artifacts", "publish_mart_assets"} <= tasks.keys()
assert tasks["generate_dbt_docs"] == ["dbt_warehouse.dbt_producer_watcher"]
assert tasks["validate_dbt_artifacts"] == []
assert tasks["publish_mart_assets"] == ["validate_dbt_artifacts"]
```

The marts DAG uses the **subset (`<=`) + per-edge** style precisely because Cosmos generates a variable number of consumer tasks. **A new test must follow that style**, e.g.:

```python
assert "check_source_freshness" in tasks
assert tasks["check_source_freshness"] == []
assert "check_source_freshness" in tasks["dbt_warehouse.dbt_producer_watcher"]
```

**What `freshness_task >> dbt_group` actually wires — MEDIUM confidence, must be confirmed against the live DagBag.**
`DbtTaskGroup` subclasses Airflow's `TaskGroup`, so `>>` sets the freshness task upstream of the group's **roots** (children with no upstream inside the group). In WATCHER mode:
- `_add_watcher_producer_task` creates `dbt_producer_watcher` and `dbt_producer_watcher_done`, with `producer >> producer_done` (`cosmos/airflow/graph.py:840-846`).
- `_add_watcher_dependencies` only links the producer to the consumer sensors when `"DbtDag" in dag.__class__.__name__` (`graph.py:896-899`). **This DAG is a plain `@dag`, not a `DbtDag`**, so that branch is skipped and the consumer sensors have **no in-group upstream** — they are also roots.

So `freshness_task >> dbt_group` most likely makes the freshness task upstream of the producer **and every consumer sensor**. That is the desired fail-closed outcome (all of them become `upstream_failed`), but the exact key set is not knowable offline. **The plan must include a step that runs `pytest tests/test_dags.py -m airflow` and records the actual `tasks` mapping before finalising the assertion.**

Also note `graph.py:917` sets `trigger_rule="always"` on consumers **only** in the `DbtDag` branch, which is skipped here — so consumers keep the default `all_success` and do fail closed. `dbt_producer_watcher_done` uses `TriggerRule.NONE_FAILED` (`cosmos/operators/_watcher/base.py:810`), which also does not run on an `upstream_failed` parent.

**Existing assertions that a new task will *not* break:** `test_marts_validation_contract` asserts the task *set* with `<=`, `dagrun_timeout == "0:45:00"`, `execution_timeout == "None"`, and filters `task_assets` down to `publish_mart_assets` only (`:215-219`). A new top-level task therefore changes **no existing assertion**, provided it declares no inlets/outlets. Adding `inlets=[CORE_ORDERS_ASSET]` to the freshness task **would** be safe against that filter but is unnecessary and out of scope.

### `tests/features/airflow_workflow_behavior.feature` + step definitions

**VERIFIED.** `tests/features/test_airflow_workflow_behavior.py` (506 lines), `pytestmark = [pytest.mark.bdd, pytest.mark.airflow]` (`:13`), run by `ci-pr.yml:218` as `pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"`.

**Architecture (this is the part a new scenario must respect):**

1. One giant `AIRFLOW_CALLABLE_SCRIPT` string (`:17-260`) is `docker exec -i de-demo-airflow python -`'d, with `__CASE__` substituted by `json.dumps(context["case"])` (`:334`).
2. Inside the container the script loads the **real DagBag** and pulls **real `python_callable`s**:
   ```python
   bag = DagBag(dag_folder="/opt/airflow/dags")
   ingestion = bag.dags["warehouse_orders_ingestion"].task_dict
   staging = ingestion["staging.validate_staging"].python_callable
   ```
3. Boundaries are faked by **monkeypatching the callable's own `__globals__`**, not by mocking libraries:
   ```python
   task_globals = staging.__globals__
   task_globals["_connect"] = lambda: Connection(counts=counts)
   ```
   There is a load-bearing comment at `:188-190`: *"The DagBag loads dags/warehouse_dbt.py as its own module object, so the callable's globals are NOT the separately imported `warehouse_dbt`."* A new case must choose `publisher.__globals__` vs `warehouse_dbt.__dict__` deliberately.
4. `Connection` / `Cursor` (`:34-66`) are hand-rolled context-manager fakes with `counts`, `fail_query`, `fail_on`, `payment_values` knobs.
5. The script prints one JSON line; the host asserts on the parsed dict (`:343`).
6. Every `@when` string is stacked on **one** `run_actual_callable` function (`:327-333`) — a new `@when` phrase is simply another decorator on that same function.
7. Gherkin lives in `airflow_workflow_behavior.feature`; `scenarios(...)` at `:11` auto-binds.

**What a freshness scenario would need — and the honest limitation.**

`check_source_freshness` is a **Cosmos operator, not a `@task`-decorated Python callable**. `task_dict["check_source_freshness"].python_callable` does not exist. The three viable framings, in descending order of value:

| Framing | What it proves | Feasibility |
|---|---|---|
| **(A) Downstream blocking is structural** — assert from the DagBag that `check_source_freshness` is upstream of `dbt_producer_watcher`, and that `validate_dbt_artifacts`'s existing barrier treats `upstream_failed` as terminal | that a freshness failure cannot reach publication | HIGH — pure DagBag inspection; but this is `tests/test_dags.py`'s job, not BDD's |
| **(B) The barrier rejects `upstream_failed`** — call the real `validate_dbt_artifacts` callable with `_metadata_task_state` patched to return `"upstream_failed"` for `dbt_warehouse.dbt_producer_watcher`, and assert it raises | the *existing* fail-closed chain still holds with a new failure origin | HIGH — pure `__globals__` patching; `terminal_failures = {"failed", "upstream_failed", "skipped", "removed"}` at `dags/warehouse_dbt.py:349` is already the mechanism. **Also needs `time.sleep` patched out**, since the loop sleeps 5s (`warehouse_dbt.py:361`) — though it raises on the first iteration here, so no sleep occurs. |
| **(C) Execute the operator** — instantiate `DbtSourceLocalOperator` and run it | the operator itself | LOW value, HIGH cost — needs a live `dwh` with staging loaded, which violates the read-only/stateful boundary for the fast BDD layer. This is what the CI job in Q4 is for. |

**Recommendation: (B).** It is the only new scenario that fits the established "real callable, faked boundary" contract, and it extends `W2`'s existing fail-closed table naturally. Proposed Gherkin, matching the file's voice:

```gherkin
  Scenario: A failed freshness gate blocks dbt artifact certification
    Given a marts run whose source freshness gate failed
    When the actual marts publisher callable runs in Airflow
    Then artifact validation refuses the run before any mart is certified
```

Implementation sketch inside `AIRFLOW_CALLABLE_SCRIPT` (new `elif` branch):

```python
elif case == "freshness_gate_blocks_certification":
    validator = bag.dags["warehouse_marts_validation"].task_dict["validate_dbt_artifacts"].python_callable
    task_globals = validator.__globals__
    task_globals["get_current_context"] = lambda: {
        "dag_run": SimpleNamespace(run_id="asset_triggered__bdd"),
        "ti": SimpleNamespace(dag_id="warehouse_marts_validation"),
    }
    # The freshness task failed, so Cosmos' producer never ran.
    task_globals["_metadata_task_state"] = lambda dag_id, run_id, task_id: (
        "upstream_failed" if task_id == "dbt_warehouse.dbt_producer_watcher" else None
    )
    error = None
    try:
        validator()
    except Exception as exc:
        error = str(exc)
    result.update(error=error)
```

with a `@then` asserting `"Warehouse dbt prerequisite failed"` in the error and `"upstream_failed"` in it. **Caveat to verify:** `validate_dbt_artifacts` is declared with `@task(execution_timeout=...)` inside the DAG function; `.python_callable` on it is the undecorated function, consistent with how `publish_mart_assets` is accessed at `:187`. That access pattern is already proven by the existing scenario.

**Do not** make existing scenarios time-dependent. Nothing in the existing fixtures touches `loaded_at`, and `replay_truncate_precedes_load` (`:246-258`) patches `_copy_csv` entirely, so it is unaffected by the new column.

---

## Q4 — CI job shape (`.github/workflows/ci-pr.yml`, `warehouse-dbt-contract`)

**VERIFIED.** Job at `ci-pr.yml:69-159`. Current step sequence:

| # | Step name | Line |
|---|---|---|
| 1 | `actions/checkout` / `setup-python` / `setup-uv` | 79–87 |
| 2 | **Install warehouse dbt runtime** — `uv venv .venv-dbt-warehouse`, `uv pip sync --require-hashes`, `cp profiles.yml.example profiles.yml` | 88–92 |
| 3 | **Install repository test dependencies** — `uv sync --locked` | 93–94 |
| 4 | **Start PostgreSQL fixture** — `docker compose --env-file .env.example up -d de-demo-postgres` + `pg_isready` loop | 95–101 |
| 5 | **Seed staging and rebuild core with the production transform** — `seed_staging.sql`, then `10_rebuild_core.sql` | 102–107 |
| 6 | **Run warehouse dbt build and docs** — `dbt parse`, `dbt build`, `dbt docs generate`, four `test -s target/*` | 108–116 |
| 7 | **Assert staging to reconciliation expectations** — `assert_marts.sql` must return zero rows | 117–125 |
| 8 | **Assert replay parity** — `replay_snapshot.sql` → `10_rebuild_core.sql` → `assert_replay_parity.sql` | 126–138 |
| 9 | **Verify repository contracts** — `pytest -q tests/test_warehouse_dbt.py` | 139–140 |
| 10 | **SQL mutation gate** — `python scripts/mutation_test.py --json mutation-report.json` | 141–144 |
| 11 | Upload mutation report / dbt artifacts | 145–156 |
| 12 | **Cleanup** — `docker compose down --remove-orphans` | 157–159 |

The job runs `bash` on `ubuntu-latest` and uses `.venv-dbt-warehouse/bin/dbt` (POSIX layout) — **not** the Windows `Scripts/dbt.exe` path.

### Where the two new steps slot in

**Insert both between step 5 (seed) and step 6 (`dbt build`).** Reasons, each grounded:

- **Fresh-pass must come after the seed and before the build**, because `seed_staging.sql` (`tests/fixtures/warehouse/seed_staging.sql`) truncates `stg.*` then inserts with **explicit column lists** (`insert into stg.customers (customer_id, …, ingest_date) values …`, and likewise for the other three). It never names `loaded_at`, so PostgreSQL supplies `now()` and the rows are seconds old at the moment freshness runs. Running the check before the seed would hit an *empty* table, which errors (see Q2(b)).
- **Stale-fail must be adjacent, with a reset immediately after**, so the backdated `loaded_at` cannot leak into any later step. It exercises the same runtime the design wants proven, and it is the only place a live database is available in this job.
- **Placing them there disturbs nothing.** Steps 6–8 read only business columns (`assert_marts.sql`, `assert_replay_parity.sql`, `replay_snapshot.sql`); `10_rebuild_core.sql` and the dbt models select named columns, never `select *` from `stg.*` (verified: the only `source('staging', …)` references in the model layer are `dbt/warehouse/models/marts/v_reconcile_sales_daily.sql:7-8`, both with explicit column projections).
- **The mutation gate is untouched.** `scripts/mutation_test.py:183-198` invokes only `dbt test --select <killer>` against a `shutil.copytree` copy of the project (`:228-245`), never `dbt source freshness` and never `dbt build`. `dbt test` does not evaluate freshness. So the mutation gate is indifferent to `loaded_at` — **provided the stale value is reset**, which the reset step guarantees regardless.
- **Do not put the new steps after step 9 or 10.** Step 8 leaves a `replay_check` schema behind and step 10 runs dbt many times; inserting a stateful `update`/reset there increases the blast radius for no benefit.

### Proposed steps (drop in after line 107)

```yaml
      - name: Source freshness — a freshly seeded batch must pass
        run: |
          .venv-dbt-warehouse/bin/dbt source freshness \
            --project-dir dbt/warehouse --profiles-dir dbt/warehouse
      - name: Source freshness — a batch older than error_after must fail closed
        run: |
          docker exec -i de-demo-postgres psql -U app -d dwh -v ON_ERROR_STOP=1 \
            < tests/fixtures/warehouse/backdate_staging_loaded_at.sql
          if .venv-dbt-warehouse/bin/dbt source freshness \
               --project-dir dbt/warehouse --profiles-dir dbt/warehouse; then
            echo "dbt source freshness exited 0 on a deliberately stale batch"
            exit 1
          fi
      - name: Reset staging load timestamps
        if: always()
        run: |
          docker exec -i de-demo-postgres psql -U app -d dwh -v ON_ERROR_STOP=1 \
            < tests/fixtures/warehouse/reset_staging_loaded_at.sql
```

Notes on that shape, each with a reason:

- **The `if ... then exit 1; fi` idiom, not `!` or `|| true`.** `bash` under `set -e` (GitHub's default is `bash -e`) makes a bare failing command abort the step; `if` suppresses `-e` for the condition, and the explicit `exit 1` makes the *expected-failure* semantics readable. This mirrors the existing `if [ -n "$violations" ]; then … exit 1; fi` pattern at `:121-125` and `:134-138`.
- **`if: always()` on the reset** so a red stale-step still restores the column before steps 6–10.
- **Backdate all four tables**, not just `stg.orders`. The design's illustrative SQL updates only `stg.orders`, which *is* sufficient to make the command exit non-zero (one error result flips `interpret_results`). But updating all four keeps the fixture honest about the "one batch, one timestamp" invariant and avoids a reader concluding the other three are exempt. Discretionary; either passes.
- **Use fixture `.sql` files under `tests/fixtures/warehouse/`, not inline SQL.** That is the established convention for every other stateful SQL in this job (`seed_staging.sql`, `assert_marts.sql`, `replay_snapshot.sql`, `assert_replay_parity.sql`), and `tests/test_warehouse_dbt.py:165-169` already asserts those paths appear in the workflow — so a new contract assertion can follow the same shape.
- **`db/init/008_stg_loaded_at.sql` applies automatically in this job.** `docker-compose.yml:31` mounts `./db/init:/docker-entrypoint-initdb.d:ro`, and the CI runner starts `de-demo-postgres` on a fresh volume, so PostgreSQL runs all of `db/init/*.sql` in filename order. `008` sorts after `007`. No bootstrap call is needed in `ci-pr.yml`.
- **A `dbt parse` sanity run already exists** at `:110`, immediately before `dbt build` — so a malformed `config:` block in `sources.yml` fails fast there regardless.

### Contract assertions to add in `tests/test_warehouse_dbt.py`

```python
workflow = read(".github/workflows/ci-pr.yml")
assert "dbt source freshness" in workflow
assert "tests/fixtures/warehouse/backdate_staging_loaded_at.sql" in workflow
assert "tests/fixtures/warehouse/reset_staging_loaded_at.sql" in workflow
```

---

## Q5 — Migration replay in `scripts/bootstrap_stack.py`

**VERIFIED.** File is 137 lines total.

### Exact current mechanics

Module constant (`:15-17`):

```python
PIPELINE_PROVENANCE_MIGRATION = (
    "/docker-entrypoint-initdb.d/007_pipeline_runs_ingestion_provenance.sql"
)
```

Note it is an **in-container absolute path** — `db/init` is bind-mounted to `/docker-entrypoint-initdb.d` (`docker-compose.yml:31`), so `psql --file` inside the container can read it even though `db/init/` only *auto-runs* on an empty data directory.

Applied inside `bootstrap()` (`:103-118`), as the last action before the success print:

```python
    _docker_exec(
        "de-demo-postgres",
        "psql",
        "-X",
        "--set=ON_ERROR_STOP=1",
        "--username",
        values["POSTGRES_USER"],
        "--dbname",
        values["POSTGRES_DB"],
        "--file",
        PIPELINE_PROVENANCE_MIGRATION,
    )
    print(
        "[OK] H1 bootstrap: network, MinIO bucket, catalog schemas, "
        "warehouse migrations, and readiness"
    )
```

`_docker_exec` (`:24-28`) shells `docker exec …` and raises `RuntimeError` on a non-zero return code. Ordering within `bootstrap()`: `wait_for_stack` → MinIO alias retry loop → `mc mb` → Trino `CREATE SCHEMA IF NOT EXISTS` → **this psql call**.

### What must change

Exactly one thing: `008_stg_loaded_at.sql` must be applied through the same `psql --set=ON_ERROR_STOP=1 --file` path. Two shapes, both faithful to "following the existing precedent":

**(a) Minimal — add a sibling constant and a second `_docker_exec`.** Smallest diff, keeps `PIPELINE_PROVENANCE_MIGRATION` intact (which matters because `tests/test_h1_runtime.py:253` asserts on the *filename literal*, and the Phase 02 planning docs reference the constant by name).

```python
STG_LOADED_AT_MIGRATION = "/docker-entrypoint-initdb.d/008_stg_loaded_at.sql"
```

**(b) Tidier — introduce a `WAREHOUSE_MIGRATIONS` tuple and loop.** Scales for 009+. **VERIFIED safe:** grep across the whole repo (excluding `.git`) finds `PIPELINE_PROVENANCE_MIGRATION` only in `scripts/bootstrap_stack.py` itself (lines 15 and 113) — the other hits are `.planning/phases/02-*/` narrative documents and `ci-h1-clean.yml`, which references the *script*, not the constant. So renaming breaks no import. Extract the `psql` invocation into a small helper to avoid repeating the eight-argument call.

Either satisfies the design. The planner should pick one and say why; **(b)** is the better long-term shape and the repo has no rule against it, but **(a)** is the smaller, more literal reading of "following the existing `PIPELINE_PROVENANCE_MIGRATION` precedent."

Both must keep `ON_ERROR_STOP=1` and both must run **after** `wait_for_stack` (PostgreSQL readiness).

**Idempotency:** `alter table if exists … add column if not exists …` is a no-op on re-run, so replaying 008 on a database that already has the column is safe — the same property `007` relies on. `bootstrap_stack.py` is itself run unconditionally by `ci-h1-clean.yml:86`.

### Is there a test asserting the replay list?

**Yes — but not where the design assumed.**

**VERIFIED:** No test asserts a *list* of migrations (no such list exists). But `tests/test_h1_runtime.py:241-256`, `test_pipeline_provenance_migration_is_additive_and_bootstrapped`, asserts the exact analogous claim for 007:

```python
assert "add column if not exists ingestion_run_id varchar" in migration
assert "create unique index" not in migration.lower()
assert "007_pipeline_runs_ingestion_provenance.sql" in bootstrap
assert 'values["POSTGRES_DB"]' in bootstrap
```

`tests/test_h1_runtime.py` is unmarked → fast suite. **This is the precedent test to extend or mirror.** Note that if shape **(b)** above is chosen, the `bootstrap` substring assertion at `:253` still passes (the filename literal survives inside the tuple), but a planner choosing **(b)** should confirm that rather than assume it.

No other test reads `db/init/002_stg_tables.sql`, and no test enumerates `db/init/`. Adding `008` breaks nothing existing.

---

## Threshold measurement — status: **UNMEASURED**

**Reported honestly, per the CONTEXT instruction.** No measurement was taken, because taking one requires running `warehouse_orders_ingestion` and observing several healthy Asset-triggered `warehouse_marts_validation` runs on the live stack — a stateful operation explicitly outside this read-only research task.

Facts available offline that bound the answer:

| Fact | Source | Bearing on the threshold |
|---|---|---|
| `dagrun_timeout=timedelta(minutes=45)` on the marts DAG | `dags/warehouse_dbt.py:329` | the pipeline already tolerates up to 45 min end-to-end |
| `execution_timeout=timedelta(minutes=40)` on `validate_dbt_artifacts` | `dags/warehouse_dbt.py:341` | a single task may legitimately poll for 40 min |
| `execution_timeout=timedelta(minutes=15)` default on ingestion tasks; `dagrun_timeout=30 min` on the ingestion DAG | `dags/warehouse_orders.py:127-131`, `:235` | ingestion itself is bounded at 30 min |
| `validate_dbt_artifacts` has **no upstream** in the graph and polls the metadata DB every 5 s | `dags/warehouse_dbt.py:341-361`, and `tests/test_dags.py:213` asserts `tasks["validate_dbt_artifacts"] == []` | adding a freshness task ahead of `dbt_group` **lengthens** this task's polling window by the freshness runtime; still far inside 40 min |

**Implication for the plan:** `warn_after: 30 minutes` sits *inside* a window the pipeline already tolerates (a 40-minute `validate_dbt_artifacts` alone would exceed it), so it will produce advisory warnings during ordinary slow-but-healthy runs. That is exactly the risk the design flagged. Two honest options:

1. **Ship the provisional values and label them provisional in W1**, with an explicit "measured basis: not yet measured; see [issue/task]" line. Warn costs nothing operationally (exit 0, gates nothing).
2. **Add a measurement task** to the plan that runs ingestion→marts three or more times on the live stack, reads elapsed time from `marts.pipeline_runs.run_ts` against the Airflow task-instance timestamps, and sets `warn_after` above the observed spread.

Option 2 is what the CONTEXT asks for; option 1 is the fallback if the stack is unavailable. **Whichever is chosen, W1 must state which, verbatim.** Do not write a sentence in W1 that implies a measurement occurred.

A useful offline observation for the measurement task: `marts.pipeline_runs` already records both `run_ts` (marts DAG, `now()` at audit time) and `ingestion_run_id` (`db/init/007_...sql:1-2`, written at `dags/warehouse_dbt.py:241-289`). Joining `run_ts` against the ingestion DagRun's end time in the Airflow metadata DB gives the elapsed figure without new instrumentation.

---

## Runtime State Inventory

This is a schema+DAG change, not a rename, but the same discipline applies — after every file in the repo is updated, what runtime state still lacks the new column?

| Category | Items found | Action required |
|---|---|---|
| **Stored data** | `stg.orders`, `stg.order_items`, `stg.order_payments`, `stg.customers` in any **existing** `dwh` volume lack `loaded_at`. `db/init/` runs only on an empty data directory (`docker-compose.yml:31`), so an existing local stack will **not** pick it up. | Apply `008` via `scripts/bootstrap_stack.py` (this is the whole point of Q5). Also note the accepted false-fresh window: `ADD COLUMN … NOT NULL DEFAULT now()` backfills existing rows with the migration timestamp. |
| **Live service config** | None. No Metabase/Superset model, Grafana dashboard, or Trino catalog references `stg.*` columns. Verified: no `select *` against `stg.*` anywhere in `dbt/warehouse/models/`, `db/pipeline_sql/`, or the fixtures. | None. |
| **OS-registered state** | None — no scheduled task, pm2 process, or systemd unit references staging columns. | None. |
| **Secrets / env vars** | None. The change adds no configuration. `DBT_POSTGRES_*` and `DWH_*` are unchanged. | None. |
| **Build artifacts / installed packages** | `dbt/warehouse/target/` (gitignored, `.gitignore:56`) holds a stale `manifest.json` whose source definitions lack the freshness config. `tests/test_warehouse_dbt.py:253-264` reads it opportunistically. A stale manifest could make a local `dbt build` skip re-parsing. | `dbt parse` (already the first command in the CI dbt step, `ci-pr.yml:110`) regenerates it. For local work, note that Cosmos copies the project to a temp dir and honours `partial_parse` (`cosmos/operators/local.py:534-540`); a `sources.yml` change invalidates the partial parse for sources, so no manual clean is required — but say so rather than leaving it implicit. |
| **CSV inputs** | `data/raw/olist_*.csv` must **not** gain a `loaded_at` header. Verified they carry `ingest_date` and that `_copy_csv` names columns explicitly (`dags/warehouse_orders.py:175-185`, column lists at `:37-91`). | None — actively verify no CSV or `STG_LOADS` entry is edited. |
| **Existing SQL fixtures** | `tests/fixtures/warehouse/seed_staging.sql` uses explicit column lists on all four inserts — unaffected. `db/pipeline_sql/00_truncate_stg.sql` is a bare `truncate table` of the four tables — unaffected. `10_rebuild_core.sql` selects named columns. | None. |

---

## Architecture Patterns

### Where the new task sits

```
warehouse_orders_ingestion  (manual)
  staging.load_raw_csv_to_stg      ← single txn: truncate + 4× COPY; now() lands in loaded_at
  staging.validate_staging         ← existing exact row-count parity, UNCHANGED
  core.rebuild_core → core.validate_core → core.publish_core_assets
        │
        └── core.orders Asset
                │
warehouse_marts_validation  (Asset-triggered)
  check_source_freshness           ← NEW  DbtSourceLocalOperator, top level
        │  >> dbt_group  (sets it upstream of the group's roots)
        ▼
  dbt_warehouse.dbt_producer_watcher   ── dbt build (WATCHER)
        ├── dbt_warehouse.<consumer sensors…>
        ├── dbt_warehouse.dbt_producer_watcher_done   (trigger_rule NONE_FAILED)
        └── generate_dbt_docs                         (trigger_rule NONE_FAILED_MIN_ONE_SUCCESS)

  validate_dbt_artifacts   ← NO graph upstream; polls the Airflow metadata DB for
                             {dbt_producer_watcher, generate_dbt_docs} states.
                             terminal_failures includes "upstream_failed".
        ▼
  publish_mart_assets      ← trigger_rule ALL_DONE; re-reads validate_dbt_artifacts'
                             state and raises if != "success". Sole publisher of the
                             four mart Assets + marts.pipeline_runs.
```

### The fail-closed chain, traced end to end (all VERIFIED)

If `check_source_freshness` fails:

1. `dbt_producer_watcher` (and the group's other roots) become `upstream_failed` — default `all_success` trigger rule; the `trigger_rule="always"` override at `cosmos/airflow/graph.py:917` applies only to `DbtDag`, not `DbtTaskGroup`.
2. `dbt_producer_watcher_done` has `TriggerRule.NONE_FAILED` (`cosmos/operators/_watcher/base.py:810`) → does not run.
3. `generate_dbt_docs` has `TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS` (`dags/warehouse_dbt.py:437`) with `dbt_producer` upstream → does not run.
4. `validate_dbt_artifacts` polls and sees `"upstream_failed"` ∈ `terminal_failures = {"failed", "upstream_failed", "skipped", "removed"}` (`warehouse_dbt.py:349`) → raises `AirflowException(f"Warehouse dbt prerequisite failed: {states}")` (`:357-358`).
5. `publish_mart_assets` (`trigger_rule=ALL_DONE`, so it *does* run) reads `validate_dbt_artifacts`' state and raises before touching the database (`:394-400`) → **`_audit_and_counts` is never called, no `marts.pipeline_runs` row, no mart Asset Metadata yielded.**

**This chain requires no modification.** The new gate plugs into an existing, tested fail-closed structure. That is the single strongest argument for the design's placement, and it belongs in W2.

One benign side effect worth a comment: because `validate_dbt_artifacts` has no graph upstream, it starts polling immediately and will now poll for the duration of the freshness check as well. Its `execution_timeout` is 40 minutes; a freshness check over four small tables is seconds. No change needed.

### Anti-patterns to avoid

- **`from cosmos.operators import DbtSourceLocalOperator`** — `ImportError`, breaks the whole DagBag (DCF-1).
- **Setting `source_rendering_behavior` on `RenderConfig`** — silently activates the experimental Watcher freshness path (`cosmos/airflow/graph.py:807-809`), which the design explicitly rejects.
- **`warn_error=True`** on the operator or as a dbt flag — collapses `warn_after` into `error_after`.
- **Attaching `callback=_persist_dbt_artifacts`** to the freshness task — copies a freshness-run `manifest.json` into the artifact sink before `dbt build` writes the real one.
- **Adding `loaded_at` to `sources.yml` `columns:` with a `not_null` test** — out of scope, adds runtime, and the DDL's `NOT NULL` already enforces it.
- **Declaring an empty `freshness: {}` on `core.*` "for symmetry"** — unnecessary (`has_freshness` is already falsy) and it invites the reader to think freshness is configured there.
- **Using `clock_timestamp()`** — explicitly forbidden; would break the one-batch-one-timestamp invariant.
- **Running `dbt source freshness` before the seed / against empty staging** — errors by construction (Q2(b)).

---

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Detecting stale staging | A custom `@task` that queries `max(loaded_at)` and compares to `now()` | `dbt source freshness` + `DbtSourceLocalOperator` | The threshold arithmetic, per-source reporting, `sources.json` artifact, and the pass/warn/error tri-state are all already implemented and version-pinned |
| Failing the Airflow task on a stale result | Parsing `target/sources.json` and raising | The operator's default `handle_exception` | Verified fail-closed by default (Q1); the design explicitly bans the fallback until proven necessary, and it is not necessary |
| Surfacing the freshness result in the UI | Custom XCom push / logging | `store_freshness_json` → the `freshness` rendered-template field | Already implemented (`cosmos/operators/local.py:422-437`) with a JSON renderer registered |
| Populating `loaded_at` per batch | Adding a column to the CSVs, or an `UPDATE` after `COPY`, or `clock_timestamp()` | PostgreSQL column `DEFAULT now()` + the existing single transaction | `now()` is transaction-start time, so all four tables get one identical value by construction rather than by coordination |
| Blocking publication on freshness failure | New guards in `publish_mart_assets` | The existing `validate_dbt_artifacts` barrier + `publish_mart_assets` state re-check | Already handles `upstream_failed`; adding a second guard would duplicate a tested invariant |
| A migration runner | A migrations table / Alembic / a new script | `scripts/bootstrap_stack.py` + idempotent `if exists` / `if not exists` DDL | The `007` precedent; `AGENTS.md` forbids adding a verification or tooling layer the change does not require |

---

## Common Pitfalls

### Pitfall 1: `ImportError` from the wrong Cosmos import path
**What goes wrong:** `from cosmos.operators import DbtSourceLocalOperator` raises, `DagBag.import_errors` becomes non-empty, `tests/test_dags.py::test_dagbag_has_no_import_errors` fails, and **every** DAG in the folder is unaffected but the marts DAG disappears.
**Why:** `cosmos/operators/__init__.py` re-exports only twelve operators; the Source operator is not among them (DCF-1).
**Avoid:** `from cosmos.operators.local import DbtSourceLocalOperator`.
**Warning sign:** the fast suite passes (it never imports Airflow) while `pytest tests/test_dags.py -m airflow` fails on `import_errors`.

### Pitfall 2: assuming the CI exit-code proof describes the Airflow runtime
**What goes wrong:** W1 says "the task gates on the CLI exit code", a reader later swaps `DBT_EXECUTABLE`, and nothing changes — because Cosmos never invokes it.
**Why:** dbt-core is installed *in the Airflow image's Python*, so `_discover_invocation_mode()` selects `DBT_RUNNER` (DCF-2).
**Avoid:** phrase the guarantee as "the dbt result status", and note that CLI exit code and `dbtRunnerResult.success` both derive from `FreshnessTask.interpret_results`.

### Pitfall 3: `warn_after` firing on ordinary orchestration lag
**What goes wrong:** healthy runs emit freshness warnings, the warning stops carrying signal, and the gate loses credibility.
**Why:** the pipeline already tolerates a 40-minute `validate_dbt_artifacts` and a 45-minute DagRun; a 30-minute warn is inside that.
**Avoid:** measure, or ship the value labelled provisional. Do not write W1 prose implying a measurement that did not happen.

### Pitfall 4: an empty staging schema fails, not passes
**What goes wrong:** a run of `dbt source freshness` at the wrong moment errors with a ~2025-year age.
**Why:** `_create_freshness_response` maps `NULL` `max_loaded_at` to `datetime(1,1,1)` (`dbt/adapters/base/impl.py:1647-1649`).
**Avoid:** only ever run freshness after `load_raw_csv_to_stg` / after the CI seed. Never add it to the mutation gate.

### Pitfall 5: the stale-fail CI step aborting the job instead of asserting
**What goes wrong:** `dbt source freshness` exits 1, GitHub's `bash -e` aborts the step, and the *expected* failure is reported as a job failure.
**Avoid:** the `if <cmd>; then echo …; exit 1; fi` idiom, matching the existing `if [ -n "$violations" ]` pattern at `ci-pr.yml:121-125`.

### Pitfall 6: leaving `loaded_at` backdated for later steps
**What goes wrong:** the mutation gate or a future freshness-touching step inherits a three-hour-old timestamp.
**Why:** the stale test mutates real rows in a shared fixture database.
**Avoid:** a reset step with `if: always()`, immediately after. (Verified low-consequence today: `scripts/mutation_test.py` only runs `dbt test`, never freshness — but that is a property of today's mutation catalogue, not a guarantee.)

### Pitfall 7: modifying `_copy_csv` or `STG_LOADS`
**What goes wrong:** naming `loaded_at` in the `COPY` column list makes PostgreSQL expect it in the CSV, and every load fails.
**Avoid:** the ingestion DAG needs **zero** changes for the timestamp to work. Verify by diff that `dags/warehouse_orders.py` is untouched by the migration commit.

### Pitfall 8: hard-coding the new DagBag `tasks` mapping without observing it
**What goes wrong:** `freshness_task >> dbt_group` links the freshness task to *all* group roots, whose identities depend on Cosmos internals; a guessed assertion is wrong.
**Avoid:** run `pytest tests/test_dags.py -m airflow` once, read the actual mapping, then write the assertion in the existing per-edge/subset style.

---

## Code Examples

### The migration (`db/init/008_stg_loaded_at.sql`) — from the approved design, verbatim

```sql
alter table if exists stg.orders
  add column if not exists loaded_at timestamptz not null default now();
alter table if exists stg.order_items
  add column if not exists loaded_at timestamptz not null default now();
alter table if exists stg.order_payments
  add column if not exists loaded_at timestamptz not null default now();
alter table if exists stg.customers
  add column if not exists loaded_at timestamptz not null default now();
```

Style precedent — `db/init/007_pipeline_runs_ingestion_provenance.sql:1-5` (VERIFIED):

```sql
alter table if exists marts.pipeline_runs
  add column if not exists ingestion_run_id varchar;

create index if not exists idx_pipeline_runs_ingestion_run_id
  on marts.pipeline_runs (ingestion_run_id);
```

No index is needed on `loaded_at`: the freshness query is a single `max()` over four small tables, and `007`'s index existed to support provenance lookups.

### The `sources.yml` block — config-level, per dbt 1.12.2 (`dbt/parser/sources.py:176-179`, `:426`)

```yaml
      - name: orders
        description: One CSV ingestion slice of order headers.
        tags: [domain:orders, layer:staging, owner:airflow]
        config:
          loaded_at_field: loaded_at
          freshness:
            warn_after:  {count: 30, period: minute}
            error_after: {count: 2,  period: hour}
        columns:
          - name: order_id
            data_tests: [not_null]
          ...
```

Repeat for `order_items`, `order_payments`, `customers`. **Nothing added under `- name: core`.** (`config:` may also be hoisted to the `staging` source level, which dbt merges down — `sources.py:391-417` — but per-table is more explicit and matches how the existing file repeats `tags:` per table.)

### The DAG change (`dags/warehouse_dbt.py`)

Import (note the path — DCF-1):

```python
from cosmos.operators import DbtDocsOperator
from cosmos.operators.local import DbtSourceLocalOperator
```

Task, reusing the existing constants as required:

```python
    # Fail-closed load-recency gate at the point of consumption. dbt exits
    # non-zero (and Cosmos' in-process dbtRunner reports success=False) only on
    # an error-level result; a warn is advisory and gates nothing.
    check_source_freshness = DbtSourceLocalOperator(
        task_id="check_source_freshness",
        project_dir=str(DBT_PROJECT_PATH),
        profile_config=_profile_config(),
        dbt_executable_path=DBT_EXECUTABLE,
        env=DBT_ENV,
        emit_datasets=False,
        install_deps=False,
    )
```

Wiring, alongside the two existing dependency statements at `warehouse_dbt.py:445-446`:

```python
    check_source_freshness >> dbt_group
    dbt_producer >> generate_docs
    validate_task >> publish_task
```

Note `dbt_producer` is resolved *after* `dbt_group` is constructed (`:439-443`), so the freshness line can go immediately after the `DbtTaskGroup(...)` call or with the other two — placing it with the other two keeps all wiring in one block.

### Backdating fixture (`tests/fixtures/warehouse/backdate_staging_loaded_at.sql`)

```sql
-- Deterministic staleness for the CI freshness gate: no sleep, no wall-clock
-- coupling. Three hours exceeds error_after (2 hours) with margin.
-- Paired with reset_staging_loaded_at.sql, which MUST run afterwards.
begin;
update stg.orders         set loaded_at = now() - interval '3 hours';
update stg.order_items    set loaded_at = now() - interval '3 hours';
update stg.order_payments set loaded_at = now() - interval '3 hours';
update stg.customers      set loaded_at = now() - interval '3 hours';
commit;
```

`reset_staging_loaded_at.sql` is the same four statements with `set loaded_at = now()`.

---

## State of the Art

| Old approach | Current approach | When changed | Impact here |
|---|---|---|---|
| `loaded_at_field:` / `freshness:` at the **top level** of a source table | Under **`config:`** | dbt 1.9–1.10 (top level now deprecated) | The design already specifies `config:`. Verified preferred in 1.12.2 at `dbt/parser/sources.py:426`. |
| `tests:` on sources | `data_tests:` | dbt 1.8 | Already adopted repo-wide (`sources.yml` uses `data_tests:`). No change. |
| Generic-test args at top level | Nested under `arguments:` | dbt 1.12 | Already adopted and asserted (`tests/test_warehouse_dbt.py:88-91`). Not touched by this phase. |
| Cosmos source freshness only as a standalone operator | Cosmos 1.15 adds Watcher-integrated freshness via `source_rendering_behavior` | Cosmos 1.15 | **Explicitly not adopted** — flagged experimental in the Cosmos docstring (`cosmos/config.py:451`) and rejected by the design. Verified inert at the current `RenderConfig`. |

**Deprecated / not applicable:**
- `dbt source snapshot-freshness` — still present as a hidden alias (`dbt/cli/main.py:832-835`) but superseded by `dbt source freshness`. Use the modern form.

---

## Project Constraints (from CLAUDE.md and AGENTS.md)

Directives the planner must honour verbatim.

| Directive | Source | Bearing on this phase |
|---|---|---|
| Run all commands from the inner `de_practicum_demo/` git root | CLAUDE.md § Repository location | all paths |
| **Never invoke bare `dbt`** — it resolves to `C:\Users\serge\anaconda3\Scripts\dbt` (wrong version, Trino adapter only) | CLAUDE.md § Invoking dbt | use `.venv-dbt-warehouse\Scripts\dbt.exe` locally, `.venv-dbt-warehouse/bin/dbt` in CI |
| Completion gate for non-doc Python changes: `uv run --locked ruff check .`, `black --check .`, `pytest` | AGENTS.md § Verification contract | required before handoff |
| DAG changes additionally require `uv run --locked ruff check dags --select AIR3 --preview` | AGENTS.md § Verification contract | `warehouse_dbt.py` is changed |
| Airflow runtime changes additionally require `pytest tests/test_h1_runtime.py`, `pytest tests/test_dags.py -m airflow`, `pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"`, plus a scheduler/triggerer/DAG-processor smoke | AGENTS.md § Verification contract | all three apply |
| Coverage gate `pytest tests --cov=iceberg --cov-fail-under=90` must stay green | AGENTS.md | this phase adds no `iceberg/` code, so the number is unchanged — but the gate still runs |
| Documentation-only changes do not need the Python gate | AGENTS.md | the W1/W2 edits alone would not, but they land with code |
| Treat Docker/Kafka/Spark/MinIO/PostgreSQL/Iceberg as **stateful**; read-only analysis must not start services or mutate tables | AGENTS.md § Runtime safety, CLAUDE.md § Working rules | governed this research; governs any local verification step |
| Behaviour changes land with focused tests **plus** `README.md` and the relevant `docs/` update | CLAUDE.md § Working rules | W1 + W2 in the same change (design also requires same-commit for W1) |
| **Do not add a test framework, task runner, wrapper script, or verification layer** unless the change explicitly requires it | AGENTS.md § Verification contract | rules out a migration runner, a freshness helper module, or a new CI job |
| Credentials come from `.env` only | AGENTS.md, CLAUDE.md | the change introduces no new credential |
| Never hand-edit a generated lock file | CLAUDE.md § Dependency management | no dependency changes in this phase, so no lock regeneration |
| `ORCHESTRATION.md` anti-overengineering ladder: `minimal-design` → implementation → tests → `simplicity-challenge` | CLAUDE.md § Working rules | favours option (a) in Q5 and argues against wrapping the operator |
| Report exactly which checks ran; never claim an unexecuted check passed | AGENTS.md | applies to the threshold measurement and to any live dbt run |

---

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json`.

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 8.x via `uv run --locked` (dev group in `pyproject.toml`); pytest-bdd for `tests/features/` |
| Config file | `pytest.ini` — `testpaths = tests`, `pythonpath = .`, `addopts = -m "not integration and not e2e and not airflow"` |
| Quick run command | `uv run --locked pytest -q tests/test_warehouse_dbt.py tests/test_h1_runtime.py` |
| Full suite command | `uv run --locked pytest` |
| Live/DagBag layer | `uv run --locked pytest tests/test_dags.py -m airflow` (requires `de-demo-airflow`) |
| BDD layer | `uv run --locked pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"` |
| dbt runtime | `.venv-dbt-warehouse/Scripts/dbt.exe` (Windows) / `.venv-dbt-warehouse/bin/dbt` (CI) — **never bare `dbt`** |

### Phase Requirements → Test Map

| Req | Behaviour | Test type | Automated command | Exists? |
|---|---|---|---|---|
| **R1** Fresh staging → freshness passes | `dbt source freshness` exits 0 seconds after the seed | live integration | `ci-pr.yml` step *"Source freshness — a freshly seeded batch must pass"* (new, after `ci-pr.yml:107`) | ❌ new CI step |
| **R1c** contract | the workflow contains the fresh-pass step | static | `pytest -q tests/test_warehouse_dbt.py` — assert `"dbt source freshness" in workflow` | ❌ new assertion |
| **R2** Stale beyond `error_after` → freshness fails | backdate 3 h, command exits non-zero | live integration | `ci-pr.yml` step *"…must fail closed"* using the `if <cmd>; then exit 1; fi` idiom | ❌ new CI step + 2 fixtures |
| **R2b** …and blocks dbt + publication | `check_source_freshness` failure ⇒ `dbt_producer_watcher` `upstream_failed` ⇒ `validate_dbt_artifacts` raises ⇒ `publish_mart_assets` refuses | behaviour (BDD, faked DB) | `pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"` — new scenario, framing **(B)** in Q3 | ❌ new scenario + step defs |
| **R2c** …structurally | `check_source_freshness` is upstream of `dbt_producer_watcher` | DagBag structure | `pytest tests/test_dags.py -m airflow` — extend `test_marts_validation_contract` in the existing per-edge style | ❌ new assertion |
| **R2d** contract | the DAG source wires the gate and imports from `cosmos.operators.local` | static | `pytest -q tests/test_warehouse_dbt.py` | ❌ new assertion |
| **R3** All four staging tables share one timestamp | one transaction ⇒ one `now()` | live integration | new assertion inside `tests/fixtures/warehouse/assert_marts.sql` **or** a dedicated `assert_loaded_at_is_one_batch.sql`: `select 'loaded_at differs across staging tables' where (select count(distinct lat) from (select distinct loaded_at lat from stg.orders union select distinct loaded_at from stg.order_items union select distinct loaded_at from stg.order_payments union select distinct loaded_at from stg.customers) t) <> 1;` — zero rows = pass, matching the file's existing violation-row convention. **Caveat:** the CI seed uses four separate `insert` statements inside one `begin;…commit;` block, so this *does* hold there. | ❌ new fixture assertion |
| **R3b** structural | `load_raw_csv_to_stg` keeps truncate + all four copies in one `with _connect()` block | behaviour (BDD) | existing scenario *"Staging load truncates before every batch…"* (`airflow_workflow_behavior.feature:78-81`) already asserts ordering and `len(order) == 5` | ✅ existing, must stay green |
| **R4** Staging row-count validation intact | exact / empty / mismatch cases | behaviour (BDD) | existing scenarios at `.feature:18-31` | ✅ existing, must stay green unchanged |
| **R5** Core/mart publication fail-closed intact | refusal + recovery + upsert | behaviour (BDD) | existing scenarios at `.feature:38-77` | ✅ existing, must stay green unchanged |
| **R6** Migration/bootstrap applies 008 | `008_stg_loaded_at.sql` is idempotent, additive, and replayed | static contract | `pytest -q tests/test_h1_runtime.py` — mirror `test_pipeline_provenance_migration_is_additive_and_bootstrapped` (`:241-256`) | ❌ new test |
| **R6b** Migration idempotency in practice | applying 008 twice is a no-op | live | `ci-h1-clean.yml` already runs `bootstrap_stack.py` against a stack whose `db/init` already applied 008 — that *is* the double-application | ✅ implicit; state it in the plan rather than adding a step |
| **R7** `core.*` declares no freshness | no `loaded_at_field` under `- name: core` | static contract | `pytest -q tests/test_warehouse_dbt.py` | ❌ new assertion |
| **R8** SQL style | fixtures and migration pass the correctness linter | static | `uv run --locked sqlfluff lint dbt/warehouse/models dbt/warehouse/tests dbt/models` (`ci-pr.yml:47`) | ✅ existing — **note:** `sqlfluff` lints only those three dirs, so `db/init/008_*.sql` and the new `tests/fixtures/` SQL are **not** linted. Do not add them; the scope is deliberate (`.sqlfluff` header). |
| **R9** dbt project still parses | `sources.yml` config block is valid | live | `ci-pr.yml:110` `dbt parse` (existing) | ✅ existing |
| **R10** dbt unit tests unaffected | 9 unit tests mocking `source('staging', …)` still pass | live | `ci-pr.yml:111` `dbt build` (existing). **Low but non-zero risk:** dbt builds source mocks from declared columns; `loaded_at` is added under `config:` only, not to any `columns:` list, and no model references it — so no fixture needs a new field. Confirm empirically at the `dbt build` step. | ✅ existing, must stay green |
| **R11** Mutation gate unaffected | 4+ mutations still killed | live | `ci-pr.yml:144` (existing). `scripts/mutation_test.py:183-198` runs only `dbt test --select <killer>`; freshness is never evaluated. | ✅ existing, must stay green |

### Sampling Rate

- **Per task commit:** `uv run --locked ruff check . && uv run --locked black --check . && uv run --locked pytest -q tests/test_warehouse_dbt.py tests/test_h1_runtime.py`
- **Per DAG-touching commit, additionally:** `uv run --locked ruff check dags --select AIR3 --preview`
- **Per wave merge:** `uv run --locked pytest` (full fast suite incl. the `--cov=iceberg` gate)
- **Phase gate (live, requires the stack):** `uv run --locked pytest tests/test_dags.py -m airflow`, then `uv run --locked pytest tests/features/test_airflow_workflow_behavior.py -m "bdd and airflow"`, then a scheduler/triggerer/DAG-processor health smoke; plus the `warehouse-dbt-contract` job green in CI.

### Wave 0 Gaps

- [ ] `tests/fixtures/warehouse/backdate_staging_loaded_at.sql` — R2
- [ ] `tests/fixtures/warehouse/reset_staging_loaded_at.sql` — R2
- [ ] R3 assertion, either appended to `tests/fixtures/warehouse/assert_marts.sql` or a new `assert_loaded_at_is_one_batch.sql` (planner's call; appending keeps the step count unchanged)
- [ ] New contract tests in `tests/test_warehouse_dbt.py` — R1c, R2d, R7
- [ ] New migration/bootstrap contract test in `tests/test_h1_runtime.py` — R6
- [ ] New DagBag assertion in `tests/test_dags.py::test_marts_validation_contract` — R2c *(must be written after observing the real `tasks` mapping — see Pitfall 8)*
- [ ] New Gherkin scenario + `@given`/`@then` steps + `elif` branch in `AIRFLOW_CALLABLE_SCRIPT` — R2b
- [ ] Two new steps + one `if: always()` reset step in `ci-pr.yml` `warehouse-dbt-contract`, inserted between lines 107 and 108 — R1, R2

No framework install is needed; every layer already exists.

---

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1`.

### Applicable ASVS categories

| ASVS category | Applies | Standard control |
|---|---|---|
| V2 Authentication | no | no auth surface added; the freshness task reuses `_profile_config()` and `DBT_ENV`, which read credentials from `.env`-sourced environment variables |
| V3 Session Management | no | no sessions |
| V4 Access Control | no | no new endpoint, role, or grant; `loaded_at` inherits the table's existing privileges |
| V5 Input Validation | **yes** | The only dynamic SQL nearby is `_copy_csv`'s f-string (`dags/warehouse_orders.py:180-181`), built from the **hard-coded** `STG_LOADS` constant — no external input. **This phase must not touch it.** The new fixture SQL is static files executed via `psql --file`, not interpolated. `loaded_at` is never user-supplied. |
| V6 Cryptography | no | none |
| V7 Error handling / logging | **yes, low** | `handle_exception_subprocess` logs `result.full_output` on failure (`cosmos/operators/local.py:303`). Under `DBT_RUNNER` (the actual runtime, DCF-2) that path is not taken; `CosmosDbtRunError` carries node names and statuses, not connection strings. dbt does not log the profile password. No new secret-exposure surface. |
| V14 Configuration | **yes, low** | The new migration is additive DDL in a file already mounted read-only (`docker-compose.yml:31` `:ro`). No new env var, no new mount, no new port. |

### Threat patterns for this stack

| Pattern | STRIDE | Mitigation status |
|---|---|---|
| SQL injection via the new fixture SQL | Tampering | **N/A** — static `.sql` files run through `psql --file` with `ON_ERROR_STOP=1`; no interpolation |
| SQL injection via `_copy_csv` table/column interpolation | Tampering | **Pre-existing, out of scope** — inputs are the module-level `STG_LOADS` constant. Do not modify. |
| Destructive fixture run against a real warehouse | Tampering / DoS | `seed_staging.sql` already aborts if `marts.pipeline_runs` is non-empty. The new backdate/reset fixtures **should carry the same guard or a header comment marking them CI-only** — a stray `update stg.orders set loaded_at = now() - interval '3 hours'` on the live `dwh` would block the next legitimate marts run. **Recommended: add the same `do $$ … raise exception … $$;` guard used by `seed_staging.sql`.** |
| Credential leakage in task logs | Information disclosure | dbt masks profile secrets; `DBT_ENV` values are passed as process env, not logged. Unchanged by this phase. |
| Gate bypass | Elevation / Repudiation | The escape hatch is **explicitly deferred**; no bypass exists. `publish_mart_assets` independently re-verifies `validate_dbt_artifacts`' state, so a stale slice cannot produce a `marts.pipeline_runs` success row. |

**Net:** no new security-relevant surface. The one actionable item is the destructive-fixture guard, which is a safety measure rather than a security control but belongs in the plan.

---

## Environment Availability

| Dependency | Required by | Available on host | Version | Fallback |
|---|---|---|---|---|
| `.venv-dbt-warehouse` (dbt-core + dbt-postgres) | live freshness check, mutation gate | ✅ `.venv-dbt-warehouse/Scripts/dbt.exe` present | dbt-core 1.12.2, dbt-postgres 1.11.0, dbt-adapters 1.24.5, dbt-common 1.39.0 (from `dist-info`) | restore via `uv pip sync --python .venv-dbt-warehouse\Scripts\python.exe --require-hashes dbt\warehouse\requirements.txt` |
| `astronomer-cosmos` 1.15.0 source | reading operator internals | ✅ **unpacked in the uv cache** at `%LOCALAPPDATA%\uv\cache\archive-v0\jI4EXMKtix3GjCyVDM-12\cosmos\` | 1.15.0 (dist-info verified) | not installed in any venv; the cache copy was sufficient for this research |
| `de-demo-airflow` container | `tests/test_dags.py -m airflow`, BDD scenarios, live DAG smoke | **not checked** — checking would require `docker ps`, and the task scope is read-only static inspection | — | the fast suite covers all static contracts; DagBag and BDD layers must run in the live phase-gate step or in CI (`airflow-dags` job) |
| `de-demo-postgres` with the `dwh` database | live `dbt source freshness`, threshold measurement | **not checked** (same reason) | — | CI `warehouse-dbt-contract` provides an ephemeral equivalent |
| `.venv-airflow` on the host | — | ✅ directory exists, but contains **no** `cosmos` or `dbt` packages | — | irrelevant; Airflow code runs in the container |
| `uv` 0.12.5 | all Python tooling | assumed present (`pyproject.toml` `required-version = "==0.12.5"`) | — | `uvx --from uv==0.12.5 uv ...` |

**Missing with no fallback:** none for planning.
**Missing with fallback:** live Airflow and PostgreSQL — the DagBag `tasks` mapping (Pitfall 8) and the threshold measurement both need them, and both are explicitly deferred to the live phase-gate step rather than guessed here.

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | `freshness_task >> dbt_group` makes the freshness task upstream of the producer **and** the consumer sensors (because the `DbtDag`-only branch at `cosmos/airflow/graph.py:896` is skipped for a `DbtTaskGroup` in a plain `@dag`) | Q3, Architecture Patterns | The `tests/test_dags.py` assertion would be written against a wrong key set. **Mitigation:** observe the real mapping before writing it (Pitfall 8). Fail-closed behaviour is unaffected either way, since the producer is a root in both readings. |
| A2 | `bash -e` is GitHub Actions' default shell mode for `run:` on `ubuntu-latest`, making the `if <cmd>; then exit 1; fi` idiom necessary | Q4 | If wrong, the naive `!` form would also work — harmless. The proposed idiom is correct under both. |
| A3 | dbt unit tests mocking `source('staging', …)` need no `loaded_at` fixture field, because it is declared only under `config:` and no model references it | Validation Architecture R10 | `dbt build` in CI would fail on a missing column. Detected immediately at `ci-pr.yml:111`; the fix is one field per fixture. Low risk. |
| A4 | The CI runner starts `de-demo-postgres` on a fresh volume every run, so `db/init/008_stg_loaded_at.sql` auto-applies without a bootstrap call | Q4 | If a cached volume existed, `loaded_at` would be missing and every freshness step would fail loudly (`relation column does not exist`) — a fail-closed, obvious error, not a silent pass. |
| A5 | `validate_dbt_artifacts`' `python_callable` is reachable via `bag.dags[...].task_dict[...].python_callable`, the same way `publish_mart_assets` is at `test_airflow_workflow_behavior.py:187` | Q3 framing (B) | The BDD scenario would need a different accessor. The `publish_mart_assets` precedent makes this very likely correct. |
| A6 | The thresholds `30 min` / `2 h` have **not** been measured against real ingestion→marts latency | Threshold section | Explicitly flagged, not hidden. W1 must say so. |
| A7 | `docker`/`de-demo-*` container availability was not probed, per the read-only stateful boundary | Environment Availability | Planning is unaffected; the live steps are scoped to the phase gate. |

---

## Open Questions

1. **What are the real ingestion→marts elapsed times?**
   - Known: the pipeline tolerates 45 min (DagRun) / 40 min (`validate_dbt_artifacts`); `marts.pipeline_runs.run_ts` and `ingestion_run_id` already exist to compute it.
   - Unclear: the actual healthy spread.
   - Recommendation: add an explicit measurement task to the plan, gated on live-stack availability, whose output is a line in W1. If it cannot run, W1 says "provisional, unmeasured" verbatim.

2. **Which file hosts the migration/bootstrap contract test?**
   - The design says `tests/test_warehouse_dbt.py`; the repository precedent is `tests/test_h1_runtime.py:241-256`.
   - Recommendation: `test_h1_runtime.py` for the migration+bootstrap assertion (same shape, same two files as the 007 precedent), `test_warehouse_dbt.py` for the `sources.yml` and DAG-wiring assertions. State the split in the plan so it is a choice, not drift.

3. **Should `bootstrap_stack.py` gain a `WAREHOUSE_MIGRATIONS` tuple, or a second constant?**
   - Verified: `PIPELINE_PROVENANCE_MIGRATION` has no external referents, so either is safe.
   - Recommendation: the second constant (option (a)) — `ORCHESTRATION.md`'s anti-overengineering ladder and AGENTS.md's "do not add a layer the change does not require" both favour it at two migrations. Revisit at three.

4. **Should the R3 same-timestamp assertion live in `assert_marts.sql` or its own fixture?**
   - `assert_marts.sql` is already the "expectations return zero violation rows" file and needs no new CI step; a separate file is more discoverable but adds a step.
   - Recommendation: append to `assert_marts.sql`, and name the violation string clearly (`'loaded_at differs across staging tables'`) so a failure reads unambiguously.

5. **Should the backdate/reset fixtures carry the `seed_staging.sql` destructive guard?**
   - Not required by the design; recommended by the Security Domain analysis.
   - Recommendation: yes — a copy of the `marts.pipeline_runs` emptiness guard. Cheap, and it prevents a stray local run from blocking the real marts DAG for two hours.

---

## Sources

### Primary — VERIFIED against the pinned artifacts (HIGH confidence)

**astronomer-cosmos 1.15.0**, unpacked wheel at `%LOCALAPPDATA%\uv\cache\archive-v0\jI4EXMKtix3GjCyVDM-12\` (version confirmed via `astronomer_cosmos-1.15.0.dist-info/METADATA`):
- `cosmos/operators/local.py` — `DbtSourceLocalOperator` (:1181-1219), `DbtLocalBaseOperator.__init__` (:205-...), `run_command` (:676-748), `handle_exception*` (:279-308), `_discover_invocation_mode` (:287-296), `_generate_dbt_flags` (:542-...), `store_freshness_json` (:422-437), `_handle_post_execution` (:626-643), `_handle_datasets` (:591-600), `_read_target_sources_json` (:124-136), `DbtDocsLocalOperator` (:1298-1322)
- `cosmos/operators/base.py` — `AbstractDbtBase.__init__` (:109-...), `DbtSourceMixin` (:433-439), `add_cmd_flags` (:283-285), `build_cmd` (:287-...), `add_global_flags` (:...)
- `cosmos/operators/__init__.py` — full 27-line export list
- `cosmos/__init__.py` — lazy-import map (:36-44, :139, :230-238)
- `cosmos/dbt/runner.py` — `is_available` (:29-36), `run_command` (:84-104), `handle_exception_if_needed` (:145-156)
- `cosmos/airflow/graph.py` — `_add_watcher_producer_task` (:786-850), `_add_watcher_dependencies` (:853-917)
- `cosmos/config.py` — `RenderConfig.source_rendering_behavior` (:75, :104, :126-133), freshness-callback docstring (:451)
- `cosmos/constants.py` — `SourceRenderingBehavior` (:143-151)
- `cosmos/operators/_watcher/base.py` — producer-done `trigger_rule=TriggerRule.NONE_FAILED` (:796-810)
- `cosmos/operators/watcher.py` — `DbtSourceWatcherOperator` (:600-...), `_check_source_freshness` handling (:204-495)

**dbt-core 1.12.2 / dbt-postgres 1.11.0**, `.venv-dbt-warehouse/Lib/site-packages/dbt/`:
- `dbt/cli/main.py` — `dbtRunner.invoke` exception mapping (:68-105), `source freshness` command (:788-835)
- `dbt/cli/requires.py` — `postflight` (:188-264)
- `dbt/cli/exceptions.py` — `CliException`, `ResultExit`, `ExceptionExit`
- `dbt/utils/utils.py` — `ExitCodes` (:43-46)
- `dbt/task/freshness.py` — `FreshnessRunner.execute` (:112-181), `FreshnessSelector` (:193-199), `FreshnessTask` (:202-232)
- `dbt/task/runnable.py` — `GraphRunnableTask.interpret_results` (:803-820)
- `dbt/task/base.py` — base `interpret_results` (:85-86)
- `dbt/artifacts/schemas/results.py` — `NodeStatus` (:58-68), `FreshnessStatus` (:89-93)
- `dbt/artifacts/resources/v1/components.py` — `FreshnessThreshold` (:175-191)
- `dbt/artifacts/resources/v1/source_definition.py` — `SourceConfig` (:20-32)
- `dbt/contracts/graph/nodes.py` — `SourceDefinition.has_freshness` (:1511-1513)
- `dbt/parser/sources.py` — config→node mapping (:168-200), config-level precedence comment (:426), freshness merge (:391-417)
- `dbt/adapters/base/impl.py` — `calculate_freshness` (:1545-1558), `_create_freshness_response` (:1644-1661)

**Repository files** (all read in full or in the cited ranges):
`dags/warehouse_dbt.py`, `dags/warehouse_orders.py`, `db/init/002_stg_tables.sql`, `db/init/007_pipeline_runs_ingestion_provenance.sql`, `db/pipeline_sql/00_truncate_stg.sql`, `scripts/bootstrap_stack.py`, `scripts/dump_dag_structure.py`, `scripts/mutation_test.py`, `dbt/warehouse/models/sources.yml`, `dbt/warehouse/dbt_project.yml`, `dbt/warehouse/profiles.yml.example`, `.github/workflows/ci-pr.yml`, `.github/workflows/ci-h1-clean.yml`, `tests/test_warehouse_dbt.py`, `tests/test_dags.py`, `tests/test_h1_runtime.py` (:230-256), `tests/features/airflow_workflow_behavior.feature`, `tests/features/test_airflow_workflow_behavior.py`, `tests/fixtures/warehouse/seed_staging.sql`, `docs/warehouse/W1-dbt-ownership.md`, `docs/warehouse/W2-execution-contract.md`, `docker-compose.yml` (:31, :107-118), `airflow.requirements.in`, `airflow.requirements.txt`, `pytest.ini`, `.sqlfluff`, `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/config.json`

### Secondary (MEDIUM confidence)
- The approved design, `docs/superpowers/specs/2026-08-17-warehouse-source-freshness-design.md` — treated as authority for *what*, cross-checked against source for *how*. Its claim that `SourceConfig` declares the three fields is **confirmed** (`source_definition.py:20-32`).

### Tertiary (LOW confidence — none used)
No web search, no Context7, no documentation-only claim. Every assertion above cites a file and line in this repository or in a pinned artifact on this machine.

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|---|---|---|
| Cosmos operator API, import path, failure semantics (Q1) | **HIGH** | read from the exact pinned 1.15.0 wheel, not documentation |
| dbt freshness exit codes (Q2) | **HIGH** | traced end to end through the installed dbt-core 1.12.2 source; every hop cited |
| Test wiring patterns (Q3) | **HIGH** for existing patterns; **MEDIUM** for the resulting DagBag graph shape | patterns read from source; the graph shape depends on Cosmos internals that need one live DagBag run to pin (A1) |
| CI job shape (Q4) | **HIGH** | full job read; the seed's explicit column lists and the mutation gate's `dbt test`-only invocation were both verified rather than assumed |
| Migration replay (Q5) | **HIGH** | `bootstrap_stack.py` is 137 lines and was read in full; the precedent test was located |
| Threshold values | **LOW / UNMEASURED** | requires a live stack; explicitly not measured and explicitly flagged (A6) |
| Security | **HIGH** | no new surface; the one recommendation (fixture guard) mirrors an existing repo pattern |

**Research date:** 2026-08-17
**Valid until:** 2026-09-16 (30 days) — all findings are against version-pinned artifacts (`astronomer-cosmos==1.15.0`, `dbt-core==1.12.2`, `dbt-postgres==1.11.0`), so they remain valid until a pin changes rather than expiring on a calendar.
