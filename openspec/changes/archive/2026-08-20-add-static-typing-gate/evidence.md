# Evidence — add-static-typing-gate (NG-0.9)

Executed 2026-08-19 on `test/dbt-extensive-testing`. Implementation commit
`b8c14af`; the receipt SHA is `5f04154` — see *Live CI*, which explains why.

First item of the bounded Next Generation `ADOPT` programme. NG-0.9's register
row now reads `2026-08-19`.

## The compatibility spike, run before anything was pinned

NG-0.9 makes mypy the contractual default and requires the spike before pinning
it, with Pyright permitted only on recorded evidence that mypy is materially
unsuitable.

**The first result was not a typing finding.** mypy refused to check anything:

```text
iceberg\common\ops.py: error: Source file found twice under different module
names: "ops" and "common.ops"
```

`iceberg/` is a `sys.path` root, not a package — `tests/conftest.py` puts it on
the path so services import as `writer.iceberg_writer`,
`medallion.iceberg_medallion` and `common.ops`. Resolved with `mypy_path`,
`explicit_package_bases` and `namespace_packages`, matching how the tests already
resolve it.

| Spike condition | Findings |
|---|---|
| `--ignore-missing-imports` | 7 errors across 7 files |
| Against pyiceberg's own `py.typed` annotations | 13 errors across 3 files |

Every finding classified as an annotation gap or a third-party model inaccuracy.
**None was a runtime defect.**

**Disposition: mypy is materially suitable.** Pyright was not evaluated further
and is not added; retaining two checkers is forbidden by the item.

`types-psycopg2` was tested before adoption — with the stubs installed, `ops.py`
produced no new errors — so psycopg2 gets real typing rather than a suppression.

## Corrections, all behaviour-identical

| Site | Finding | Action |
|---|---|---|
| `iceberg_writer.py` `read_batch` | annotated `-> object` while every caller uses `.num_rows` | annotate `-> pa.Table`; annotate the heterogeneous `missing` list |
| `iceberg_medallion.py:1311` | bare `return` in a `-> dict \| None` function | `return None` |
| `ops.py` `Metrics.record` | `bronze_rows: int` while the medallion passes `None`, with a comment saying so | widen to `int \| None` |
| `ops.py` `_RuntimeMetrics.__init__` | `int(port)` where `port: str \| None`; mypy cannot narrow through `self.enabled` | narrow on `port` — identical condition, since `self.enabled = bool(port)` on the line above |

`read_batch` is the one that matters: its annotation was **wrong**, and Ruff has
no way to notice a function annotated `object` whose result is attribute-accessed.
That is the gap NG-0.9 exists to close, demonstrated on real code rather than a
fixture.

## Where production code was deliberately not changed

pyiceberg's `In.__new__(cls, term, literals)` is the real, documented
constructor. `In` is a pydantic model, so mypy reads the generated `__init__` and
rejects the documented call form at three sites.

The item states that production behaviour SHALL NOT change to satisfy an
incorrect type model. These three sites decide Silver's current state and are
covered by the M3/M4 integration suites. The keyword form
`In(term=..., values=...)` would *probably* satisfy both mypy and the runtime —
"probably" is not a standard to apply to code that determines business state.

Three narrow suppressions with their exact error codes and one shared
explanation. `warn_unused_ignores = true` turns each into an error once pyiceberg
corrects its model.

**That setting earned its place immediately**: it rejected the first, broader
attempt —

```text
error: Unused "type: ignore[arg-type]" comment  [unused-ignore]
```

— forcing each suppression onto the exact line mypy attributes the error to.

## Configuration

- Typed scope declared as `files = ["iceberg"]`, the production core the 90%
  coverage gate already guards.
- `warn_unused_configs`, `warn_redundant_casts`, `warn_unused_ignores`,
  `no_implicit_optional`.
- `ignore_missing_imports` scoped **by name** to `pyarrow.*`, `pyiceberg.*` and
  `prometheus_client.*` — the three that ship no `py.typed`. No global setting,
  no `ignore_errors`, no file exclusions.

## Negative proof — the gate catches what Ruff does not

`tests/test_typing_gate.py`. A function annotated `-> int` returning `rows[0]`:

| Assertion | Result |
|---|---|
| Ruff exits 0 on the fixture | passes — otherwise it would demonstrate no gap |
| mypy exits non-zero with `return-value` | passes |

Plus two `architecture` tests pinning that the scope stays declared, the checker
stays pinned, `warn_unused_ignores` stays on, `ignore_errors` never appears, the
third-party suppressions stay enumerated, and psycopg2 stays out of them.

## Local gates

| Check | Result |
|---|---|
| `ruff check .` | `All checks passed!` |
| `black --check .` | 78 files unchanged |
| `mypy` | `Success: no issues found in 7 source files` |
| `pytest tests --cov=iceberg --cov-fail-under=90` | **421 passed**, 70 deselected, coverage **94.29%** |
| Test delta | 417 → 421, exactly the four added tests |
| Coverage delta | none |
| Lock idempotence | re-running `scripts/lock-python-dependencies.sh` is a no-op |

## Live CI

**`b8c14af`'s `CI` run was cancelled, not failed.** Pushing the archive commit
for the preceding change superseded it under GitHub's concurrency policy while it
was still running. `M5 architecture gates`, `S1 dbt semantic lineage` and
`H1 clean reproducible stack` all completed **success** on `b8c14af`.

The receipt for the typing gate is therefore **`5f04154`**, which contains every
line of NG-0.9's implementation plus the preceding change's archive:

| Workflow | Conclusion |
|---|---|
| CI | success |
| M5 architecture gates | success |
| S1 dbt semantic lineage | success |
| H1 clean reproducible stack | success |

The claim that matters was verified per-step rather than by the job's colour —
run `32307424827`, `Lint + compose validation`:

```text
success  Ruff
success  Black
success  mypy (typed scope declared in pyproject.toml)
success  SQLFluff
success  Verify committed dependency locks
```

The type check executed and passed in CI, and the lock verification confirms the
regenerated `uv.lock` and `requirements-dev.txt` are not stale.

## Scope fence

`git diff --exit-code dags/ dbt/ spark/ kafka/ observability/ scripts/ .planning/ docker-compose.yml docker-compose.extended.yml`
— exit 0. Those surfaces are onboarded by their own changes.

## Findings recorded rather than papered over

- **The typed scope is one package.** `dags/`, `scripts/`, `spark/`, `kafka/`
  and `observability/` are unchecked. A green mypy run does not mean the
  repository is typed, which is why the scope is declared in `pyproject.toml` and
  asserted by a test.

- **Four production files were edited by a tooling change.** The item's non-goals
  forbid rewriting working code to reach strict typing. Four one-line annotation
  corrections are not that, but the boundary is a judgement and it was exercised.
  Suppressing all four instead would have left the checker green while hiding
  that `read_batch`'s annotation was actually wrong.

- **Pinning mypy pins its diagnostics.** A later version will find more; that
  upgrade becomes a change with its own evidence rather than a silent drift.

## Deliberately not done

- Pyright not added, not configured, not evaluated beyond the spike.
- No global `ignore_missing_imports`, no `ignore_errors`, no file exclusions.
- Coverage threshold unchanged; no test weakened, skipped or xfailed.
- No other first-party surface onboarded into typed scope.
- No NG item beyond this one begun.
