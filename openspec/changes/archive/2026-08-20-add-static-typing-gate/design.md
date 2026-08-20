## Context

NG-0.9 names mypy as the contractual default and requires a compatibility spike
before pinning it, with Pyright permitted only on recorded evidence that mypy is
materially unsuitable. The spike was run first; everything below follows from it.

## The compatibility spike

`uvx mypy==1.18.2` over `iceberg/`, before any code change.

The first run failed outright — `Source file found twice under different module
names: "ops" and "common.ops"`. That is a layout fact, not a typing one:
`iceberg/` is a `sys.path` root rather than a package, because `tests/conftest.py`
puts it on the path so services import as `writer.iceberg_writer`,
`medallion.iceberg_medallion` and `common.ops`. With `mypy_path=iceberg`,
`explicit_package_bases` and `namespace_packages`, mypy resolves the tree the way
the tests do.

Findings then: **7 errors across 7 files** with missing-import noise suppressed,
and **13** once pyiceberg's own `py.typed` annotations were in play. Both numbers
are small, and every one resolved to an annotation gap or a third-party model
inaccuracy — no runtime defect, no unresolvable conflict.

**Disposition: mypy is materially suitable. Pyright is not evaluated further and
is not added.** Retaining two checkers is forbidden by the item.

## Decisions

**Typed scope is `iceberg/` and nothing else, initially.** It is the production
core, it is what the 90% coverage gate already guards, and all seven modules
already carry `from __future__ import annotations`. `dags/`, `scripts/`,
`spark/`, `kafka/` and `observability/` are onboarded by their own changes; the
item requires the scope to be *listed* and to expand monotonically, not to start
complete.

**Four annotation corrections rather than four suppressions.** Each is
behaviour-identical:

- `read_batch(...) -> object` was simply wrong — it returns a `pa.Table` and
  every caller uses `.num_rows`. Ruff cannot see this; a checker must.
- A bare `return` in a `-> dict | None` function. mypy requires `return None`
  even when the type admits it — verified against a throwaway probe rather than
  assumed. Runtime behaviour is identical.
- `Metrics.record(bronze_rows: int = 0)` while the medallion passes `None`, with
  a comment at the call site saying so. The annotation was the only thing
  claiming it could not be `None`; psycopg2 sends NULL and always has.
- `if not self.enabled` becomes `if not port`. Identical condition —
  `self.enabled` was assigned `bool(port)` on the line above — but a checker can
  narrow the second.

**Three coded suppressions for pyiceberg's `In`, and the call sites are left
exactly as they are.** `In.__new__(cls, term, literals)` is the real, documented
constructor; `In` is a pydantic model, so mypy reads the generated `__init__` and
rejects the documented call form. The item is explicit that production behaviour
SHALL NOT change to satisfy an incorrect type model, and these three sites
determine Silver's current state — they are covered by the M3/M4 integration
suites and are not worth rephrasing to please a wrong model. The keyword form
`In(term=..., values=...)` would probably satisfy both, but "probably" is not a
standard to apply to the code that decides business state.

Each suppression carries its narrow error codes and a shared explanation.
`warn_unused_ignores = true` means any of them that stops being needed — when
pyiceberg fixes its model — becomes an error rather than lingering.

**`types-psycopg2` instead of a fourth suppression.** The item prefers stubs over
ignores where practical. It was tested before adoption: with the stubs installed,
`ops.py` produced no new errors.

**Third-party overrides are enumerated, not global.** `ignore_missing_imports`
applies to `pyarrow.*`, `pyiceberg.*` and `prometheus_client.*` by name — the
three that ship no `py.typed`. A global setting would hide a genuinely missing
first-party import just as readily.

**The negative fixture is a type error that Ruff accepts.** A function annotated
`-> int` returning `rows[0]`. The test asserts both halves — Ruff exits 0, mypy
exits non-zero with `return-value` — because a fixture that merely fails mypy
would not demonstrate the gap the item exists to close.

**CI places the step beside Ruff and Black**, in the lint job, ahead of the test
job. The item requires a type failure to be diagnosable without starting the
stack, and that job starts nothing.

## Risks / Trade-offs

**Four production files changed by a tooling item.** The item's non-goals forbid
rewriting working code to reach strict typing; four one-line annotation
corrections are not that, but the boundary is a judgement and it was exercised.
The alternative — suppressing all four — would have left the checker green while
telling the reader nothing, and would have hidden that `read_batch`'s annotation
was actually wrong.

**Scope is one package.** The gate is real but narrow: `dags/` and `scripts/`
remain unchecked, and a reader could mistake a green mypy run for repository-wide
typing. The scope is declared in `pyproject.toml` and asserted by a test, so it
is at least visible.

**Pinning mypy pins its diagnostics.** A future mypy will find more; the upgrade
will be a change with its own evidence rather than a silent drift, which is what
pinning is for.
