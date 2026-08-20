## 1. Compatibility spike, before anything is pinned

- [x] 1.1 Establish the baseline: seven first-party modules in `iceberg/`, all already carrying `from __future__ import annotations`; no type checker in `pyproject.toml`
- [x] 1.2 Run mypy without touching the repository; hit and diagnose the `Source file found twice` layout failure
- [x] 1.3 Resolve the layout the way `tests/conftest.py` does — `mypy_path`, `explicit_package_bases`, `namespace_packages`
- [x] 1.4 Record the finding counts: 7 with import noise suppressed, 13 against pyiceberg's real annotations
- [x] 1.5 Classify every finding as annotation gap or third-party model inaccuracy; confirm none is a runtime defect
- [x] 1.6 Disposition: mypy is materially suitable; Pyright is not evaluated further and is not added

## 2. Pin and configure

- [x] 2.1 `mypy==1.18.2` in the dev group
- [x] 2.2 Test `types-psycopg2` before adopting it; confirm it introduces no new errors, then pin it
- [x] 2.3 `[tool.mypy]` with the typed scope declared as `iceberg/`
- [x] 2.4 `warn_unused_ignores`, `warn_redundant_casts`, `warn_unused_configs`, `no_implicit_optional`
- [x] 2.5 Enumerate the three packages shipping no `py.typed`; do not set a global `ignore_missing_imports`
- [x] 2.6 Regenerate `uv.lock` and `requirements-dev.txt` with the repository lock script

## 3. Make the typed scope green truthfully

- [x] 3.1 `read_batch` returns `pa.Table`, and annotate the heterogeneous `missing` list
- [x] 3.2 Bare `return` becomes `return None`, after verifying mypy's rule against a throwaway probe
- [x] 3.3 `Metrics.record` widens `bronze_rows` and `duplicates_removed` to `int | None`, matching what the medallion already passes
- [x] 3.4 Narrow on `port` rather than `self.enabled` — identical condition
- [x] 3.5 Three coded suppressions for pyiceberg's `In`, call sites unchanged, with one shared explanation
- [x] 3.6 Place each suppression on the exact line mypy attributes the error to; `warn_unused_ignores` rejected the first, broader attempt
- [x] 3.7 `uv run --locked mypy` clean over seven files

## 4. Prove the gate does something

- [x] 4.1 Negative fixture: a return-type error that Ruff accepts
- [x] 4.2 Assert Ruff exits 0 on it — otherwise it demonstrates no gap
- [x] 4.3 Assert mypy exits non-zero with `return-value`
- [x] 4.4 `architecture` test: scope stays declared, checker stays pinned, `warn_unused_ignores` stays on, `ignore_errors` never appears
- [x] 4.5 `architecture` test: third-party suppressions stay enumerated, and psycopg2 stays out of them

## 5. Integrate

- [x] 5.1 CI step beside Ruff and Black, in the lint job, before the test job
- [x] 5.2 `AGENTS.md` completion gate gains `uv run --locked mypy`, with the monotonic-scope and suppression rules
- [x] 5.3 `CLAUDE.md` records the `sys.path`-root caveat that makes the config necessary
- [x] 5.4 Flip NG-0.9's register row to its authorisation date

## 6. Gates and closure

- [x] 6.1 ruff, black, mypy, pytest with the coverage gate
- [x] 6.2 Confirm coverage unchanged and no test weakened
- [x] 6.3 Backlog validation and strict OpenSpec validation
- [x] 6.4 Scope fence
- [x] 6.5 Commit, push, confirm live CI including the new step
- [x] 6.6 Evidence, archive, push
- [x] 6.7 Re-read the canonical sources and select the next programme item
