## Authorisation

Covered by the bounded Next Generation `ADOPT` programme authorisation recorded
on 2026-08-19 in `authorise-bounded-autonomous-programme`. NG-0.9's register row
now carries that date.

This is the programme's first item, selected as ADR-0003's Wave 1 head. NG-0.9
has no hard dependency — established in
`reconcile-next-generation-hard-dependencies`, which is what unblocked it.

## Why

Ruff is a linter, not a type checker, and its own documentation says so. The
repository pins Ruff, Black, SQLFluff, pytest and a 90% coverage gate, and has no
type checker at all — the one gap NG-0.9 exists to close.

The cost of closing it rises monotonically. Every later NG item adds first-party
Python: lineage emitters, OTel instrumentation, metadata adapters, agent tools,
scorers. Landing the gate first makes those typed by default; landing it later
means retro-typing them.

## What Changes

- **mypy 1.18.2 pinned** in the dev group, with `types-psycopg2` for real
  psycopg2 typing rather than a suppression.
- **`[tool.mypy]` in `pyproject.toml`**: typed scope declared as `iceberg/`, plus
  the three settings that make `iceberg/` resolvable at all — it is a `sys.path`
  root, not a package, so without `mypy_path`, `explicit_package_bases` and
  `namespace_packages` mypy finds `common/ops.py` under two module names and
  refuses to check anything.
- **Four annotation corrections**, all behaviour-identical, found by the checker:
  `read_batch` annotated `-> object` while callers used `.num_rows`; a bare
  `return` in a `-> dict | None` function; `Metrics.record` declaring
  `bronze_rows: int` while the medallion documents passing `None`; and a
  narrowing that reads `port` rather than `self.enabled`.
- **Three narrow, coded suppressions** for pyiceberg's `In`, whose pydantic
  `__init__` mypy reads instead of its real `__new__`.
- **Negative fixture** proving the checker catches what Ruff accepts, plus two
  `architecture` tests pinning that the scope stays declared and the third-party
  suppressions stay enumerated.
- **CI**: a `mypy` step beside Ruff and Black in the fast lint job, before the
  test job.
- **Contract**: `AGENTS.md`'s completion gate gains `uv run --locked mypy`.

**Scope fence:**

- No runtime behaviour changes. Every `iceberg/` edit is an annotation, a
  narrowing that preserves the identical condition, or a coded suppression.
- No second type checker. Pyright is not added; the compatibility spike found
  mypy materially suitable.
- No blanket `ignore_missing_imports`, no `ignore_errors`, no file exclusions.
- Coverage threshold unchanged; no test weakened.
- `git diff --exit-code dags/ dbt/ spark/ kafka/ observability/ scripts/ .planning/ docker-compose*.yml`
  SHALL be clean — those surfaces are onboarded by their own changes.

## Capabilities

### Modified Capabilities

None. `verification-contract` already governs what counts as verified and names
`AGENTS.md` as the canonical command list; this change adds a command to that
list rather than a rule about it.

## Impact

- `pyproject.toml`, `uv.lock`, `requirements-dev.txt` — mypy and stubs pinned.
- `iceberg/` — four annotation corrections, three suppressions.
- `tests/test_typing_gate.py` — new.
- `.github/workflows/ci-pr.yml` — one step.
- `AGENTS.md`, `CLAUDE.md` — the contract and the layout caveat.
- `openspec/backlog/next-generation/00-INDEX.md` — NG-0.9's authorisation date.
