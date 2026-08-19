# Evidence — add-next-generation-backlog

Executed 2026-08-19 on `test/dbt-extensive-testing`. Landed across two commits:
`d8a3015` (initial package) and the governance-hardening commit that follows it.

Authorised by the operator on 2026-08-19, for this change only. All fourteen
backlog items remain `Authorised: no`.

## What landed

| Path | Files |
|---|---|
| `openspec/backlog/README.md` | 1 — surfaces table, rules, promotion contract, structural-check command |
| `openspec/backlog/validate_backlog.py` | 1 — standalone structural check |
| `openspec/backlog/next-generation/` | 15 — `00-INDEX.md` register + NG-0.1 … NG-2.2 |
| `openspec/changes/add-next-generation-backlog/` | 5 + spec delta (4 requirements) |
| `AGENTS.md`, `CLAUDE.md` | 1 pointer each |

## Completion gate

This change adds a Python file, so the full gate applies rather than the
documentation exemption.

| Check | Command | Result |
|---|---|---|
| Lint | `uv run --locked ruff check .` | `All checks passed!` |
| Format | `uv run --locked black --check .` | 76 files unchanged |
| Tests + coverage | `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | **409 passed**, 67 deselected, coverage **94.29%** (threshold 90%) |
| Backlog structure | `uv run --locked python openspec/backlog/validate_backlog.py` | `backlog validation OK (14 items)` |
| Change validity | `openspec validate add-next-generation-backlog --strict` | valid |
| Standing specs | `openspec validate --specs --strict` | 2 passed, 0 failed |

The added script sits outside `iceberg/`, so the coverage denominator is
unchanged; 94.29% matches the pre-change figure.

## Scope fence

```bash
git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ \
  tests/ scripts/ .planning/ docker-compose.yml docker-compose.extended.yml \
  pyproject.toml uv.lock .github/
```

Exit 0 — clean. Every modified path is inside the authorised set
(`openspec/backlog/**`, `openspec/specs/engineering-governance/**`, `AGENTS.md`,
`CLAUDE.md`, this change's own artifacts).

## Negative proof of the structural check

Seven mutations applied to a **scratch copy** of the backlog under the session
scratchpad — the tracked backlog was never mutated. Each was reverted before the
next was applied, and the restored copy passes.

| Mutation | Exit | Message |
|---|---|---|
| Duplicate change id | 1 | `line 46: change id 'add-tempo-trace-backend' is already assigned to NG-0.5` |
| Dependency cycle (`NG-0.4 → NG-0.7`) | 1 | `dependency cycle: NG-0.4 -> NG-0.7 -> NG-0.4` |
| Order violation (`NG-0.2` depends on `NG-0.8`) | 1 | `line 42: NG-0.2 depends on NG-0.8, which appears later in the register; row order is not a valid execution order` |
| `Authorised` flipped to `yes` | 1 | `line 41: NG-0.1 authorised cell is 'yes'; expected 'no' or an ISO date` |
| Unknown dependency `NG-3.7` | 1 | `line 46: NG-0.6 depends on unknown item 'NG-3.7'` |
| Invalid gate `MAYBE` | 1 | `line 52: gate 'MAYBE' is not one of ['ADOPT', 'EXPERIMENT']` |
| Freshness section removed from an item | 1 | missing required marker `'## Freshness of external assumptions'` |
| **Restored copy** | **0** | `backlog validation OK (14 items)` |

## Derived layering matches the published layering

The validator computes longest-path layers from the register and prints them.
The index publishes the same layering as prose. They agree exactly:

```text
layer 0   NG-0.1
layer 1   NG-0.2, NG-0.4, NG-0.9
layer 2   NG-0.3, NG-0.5, NG-0.6
layer 3   NG-0.7
layer 4   NG-0.8, NG-1.1
layer 5   NG-1.2, NG-2.1
layer 6   NG-1.3, NG-2.2
```

This replaced a hand-drawn ASCII graph that **did** disagree with the table once
the dependency column was normalised: it showed NG-1.2 depending on NG-1.1,
which NG-1.2's own text calls a preference, not a requirement.

## Findings recorded rather than papered over

- **NG-1.1 contradicts itself.** Its `Dependencies` section lists "NG-0.1
  through NG-0.7" — which includes NG-0.3 — and then calls OpenMetadata
  "recommended before adoption". The register takes the stricter reading
  (NG-0.3 is a hard dependency), because over-gating can only delay work whereas
  under-gating can start it prematurely. The contradiction is **not resolved
  here**; it is handed to `evaluate-flink-shadow-streaming`, since deciding
  NG-1.1's scope inside a governance change would breach this change's fence.

- **The structural check is not enforced by CI.** `tests/` is in the forbidden
  set of the authorised fence, so the checker ships as a standalone script
  rather than as an `architecture`-marked fitness test beside the M5 gates —
  which is where the repository's idiom says it belongs. Consequence stated
  plainly: today it catches a broken register only when someone runs it.
  Deferred to its own change and recorded in the backlog README, not only here.

- **The register is now a parsing target.** Reformatting the table breaks the
  checker. Accepted deliberately; the column contracts are documented inside the
  register so the constraint is discoverable where the table is edited.

- **NG-0.9's premise was re-checked and still holds.** `pyproject.toml` pins
  `black==25.9.0`, `ruff==0.12.0`, `sqlfluff==3.4.2`, `pytest==8.4.2`, and no
  type checker. The stray `.mypy_cache/` at both repository levels is from an
  ad-hoc invocation and is not a configured gate.

- **The other thirteen premises were not re-verified**, deliberately. Verifying
  a gap belongs to each item's own change, and a dated "what exists today" note
  inside a backlog document is worse than none because it reads as verified.
  The *Freshness of external assumptions* section now makes that revalidation an
  obligation on whoever promotes the item, rather than a courtesy.

## Live CI

Not obtained. The branch tracks a fork remote and the repository's six workflows
trigger on pull requests and on pushes to `main`; none of them fires for a push
to this branch, and no pull request exists for it. **No claim of a green live CI
run is made for this change.** The gate figures above were produced locally by
the commands shown.

## Deliberately not done

- No backlog item is authorised. All fourteen `Authorised` cells read `no`,
  asserted by the structural check rather than by inspection.
- No item was copied into `openspec/changes/` as a proposal.
- NG-0.9 was not started, despite being the cheapest of the fourteen and despite
  this change touching lint/format tooling questions.
- `tests/`, `pyproject.toml`, `uv.lock` and the CI workflows were not edited.
- `.planning/` was not edited. The open `04-09` / BENCH-01 obligation recorded
  there is untouched and remains unauthorised.
- NG-1.1's dependency contradiction was not resolved.
