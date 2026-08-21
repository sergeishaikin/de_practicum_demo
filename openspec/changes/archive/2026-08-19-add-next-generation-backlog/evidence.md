# Evidence — add-next-generation-backlog

Executed 2026-08-19 on `test/dbt-extensive-testing`, across three commits:
`d8a3015` (the package), `7d9977d` (checkable register, non-chaining
authorisation, freshness obligation), and the archive commit that closes it.

Authorised by the operator on 2026-08-19, for this change only. All fourteen
backlog items remain `Authorised: no`.

## What landed

| Path | Files |
|---|---|
| `openspec/backlog/README.md` | 1 — surfaces table, rules, promotion contract, structural-check command |
| `openspec/backlog/validate_backlog.py` | 1 — standalone structural check |
| `openspec/backlog/next-generation/` | 15 — `00-INDEX.md` register + NG-0.1 … NG-2.2 |
| `openspec/changes/add-next-generation-backlog/` | 5 + spec delta (5 requirements) |
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

- **Two items contradict the register, and neither is resolved here.** NG-1.1's
  `Dependencies` section lists "NG-0.1 through NG-0.7" — which includes NG-0.3 —
  and then calls OpenMetadata "recommended before adoption". NG-1.2's dependency
  sentence is weaker than its register row. The register carries the stricter
  reading in both cases, explicitly labelled **interim**, because over-gating can
  only delay work whereas under-gating can start it prematurely.

  An earlier draft handed both to the implementing change's design to settle.
  That was corrected: a fifth governance requirement now makes a discovered
  contradiction *stop* the change that finds it, to be resolved as a bounded
  backlog correction or a recorded authoritative interpretation before that
  change's design is accepted. Letting an implementation pick a reading
  retroactively rewrites what the backlog meant, and it will naturally pick
  whichever reading suits the work already done.

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

**Obtained, and green.** An earlier draft of this evidence file claimed the
opposite — that no workflow could trigger for this branch. That was wrong: pull
request #1 is open on `test/dbt-extensive-testing`, so every push to the branch
fires the PR-triggered workflows. The claim was written from the branch's
tracking remote without checking for an open PR.

All four workflows that trigger for this branch completed successfully on
`7d9977d`, the SHA carrying the full backlog and governance content:

| Run | Workflow | Conclusion |
|---|---|---|
| 32287628478 | CI | success |
| 32287628412 | M5 architecture gates | success |
| 32287628411 | S1 dbt semantic lineage | success |
| 32287628419 | H1 clean reproducible stack | success |

The preceding commit `d8a3015` was also green on the two workflows its paths
triggered (M5 architecture gates, S1 dbt semantic lineage).

The archive commit that follows carries no content beyond merging this change's
spec delta into `openspec/specs/engineering-governance/spec.md` and moving the
change directory into `changes/archive/`; its own run is reported at handoff
rather than recorded here, since a receipt cannot contain the result of the
commit that writes it.

## Note for the operator, not a finding

PR #1 is titled *"Phase 3: staging source freshness gate (+ dbt testing-layer
docs)"*. The backlog and governance commits are landing on a pull request whose
title describes unrelated work. Whether to split them into their own PR or
retitle #1 is the operator's call; nothing was changed on that basis.

## Deliberately not done

- No backlog item is authorised. All fourteen `Authorised` cells read `no`,
  asserted by the structural check rather than by inspection.
- No item was copied into `openspec/changes/` as a proposal.
- NG-0.9 was not started, despite being the cheapest of the fourteen and despite
  this change touching lint/format tooling questions.
- `tests/`, `pyproject.toml`, `uv.lock` and the CI workflows were not edited.
- `.planning/` was not edited. The open `04-09` / BENCH-01 obligation recorded
  there is untouched and remains unauthorised.
- Neither dependency contradiction (NG-1.1, NG-1.2) was resolved; both are
  recorded with interim readings and a rule that stops the change which finds
  them.
- No ADR was written. Recording the programme prioritisation is a separate,
  programme-level decision and is deliberately not mixed into the change that
  establishes backlog governance.
