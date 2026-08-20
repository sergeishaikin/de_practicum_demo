# Evidence — record-next-generation-prioritisation

Executed 2026-08-19 on `test/dbt-extensive-testing`, immediately after
`add-next-generation-backlog` archived.

Authorised by the operator on 2026-08-19, conditioned on that archive. Condition
satisfied before work began.

## Preconditions verified before writing

| Precondition | Check | Result |
|---|---|---|
| Prior change archived | `openspec list` | `No active changes found` |
| Working tree clean | `git status --porcelain \| wc -l` | `0` |
| Programme still unauthorised | `grep -c '\| no \|$'` on the register | `14` |
| Layering machine-sourced | `validate_backlog.py` | layers 0–6 as published; the ADR's layer table is copied from this output, not from prior prose |
| ADR numbering convention | `ls docs/adr` | `0001-…`, `0002-…` → `0003-next-generation-backlog-prioritisation.md`, not the informal `ADR-0003-` form |

## What landed

| Path | Content |
|---|---|
| `docs/adr/0003-next-generation-backlog-prioritisation.md` | The ADR |
| `openspec/changes/record-next-generation-prioritisation/` | proposal, design, tasks, evidence, `.openspec.yaml` |

## Scope fence

Three separate assertions, all exit 0:

```bash
git diff --exit-code openspec/backlog/ openspec/specs/
git diff --exit-code docs/adr/0001-incremental-silver-and-gold.md \
                     docs/adr/0002-steady-state-shadow-policy.md
git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ \
  tests/ scripts/ .planning/ docker-compose.yml docker-compose.extended.yml \
  pyproject.toml uv.lock .github/
```

The first is the one that matters most for this change: it records a view *about*
the backlog without editing it. No `Authorised` cell moved, no register row
reordered, no item text changed.

## Checks

| Check | Command | Result |
|---|---|---|
| Change validity | `openspec validate record-next-generation-prioritisation --strict` | valid |
| Standing specs | `openspec validate --specs --strict` | 2 passed, 0 failed |
| Backlog structure | `uv run --locked python openspec/backlog/validate_backlog.py` | `backlog validation OK (14 items)` |
| Authorisation state after landing | `grep -c` on the register | 14 items still `no` |

### Checks not executed, and why

- **Python completion gate** (`ruff`, `black`, `pytest`, coverage). Not run and
  not applicable: this change touches no Python, no executable command and no
  configuration example, which is the exemption `AGENTS.md` states. The previous
  change did add Python and therefore did run the full gate.
- **Live stack, integration, E2E, M5/H1/S1 gates.** Not run, no runtime surface
  involved. CI runs them anyway on push, and their outcome is recorded below.

## One rejected-then-corrected step

`openspec validate --strict` initially failed:

```text
✗ [ERROR] Change must have at least one delta. No deltas found.
```

That default is correct — a change that silently modifies no capability is
usually one that forgot to declare what it changed. The legitimate case has an
explicit mechanism, `skip_specs: true` in `.openspec.yaml`, which this change now
sets. Recorded because the distinction is the point: the absence of a spec delta
here is a **declared property** of a documentation change, not an omission that
happened to pass validation.

Adding a requirement purely to satisfy the validator was considered and rejected.
Every rule this ADR obeys — priority is not authorisation, ordering does not
chain, premises are revalidated at promotion — was ratified by
`add-next-generation-backlog`. Restating one of them here would produce two
statements of a single rule that can drift apart, which is the defect the
register was restructured to remove.

## Findings recorded rather than papered over

- **"Critical path" was the wrong term and is not used.** The earlier analysis
  called `0.9 → 0.1 → 0.2 → 0.3 → 0.7 → 0.8 → 2.1 → 2.2` the critical path. That
  asserts a single longest path to a fixed terminus, and this programme has none:
  `NG-1.3` may end in `DO NOT IMPLEMENT`, the `1.x`/`2.x` fork is genuine, and any
  `EXPERIMENT` item may end in `REMOVE` — which the register's invariant 10 calls
  a successful outcome. The ADR says "recommended path to the first
  differentiated end-state" and states why.

- **Every cost and resource figure is relative and unmeasured.** No profile
  receipt exists for any NG capability because none has been built — `NG-0.1` is
  the item that would require them. The S/M/L/XL sizings and the resource ceiling
  are judgements, and the ADR says so in the parallelism section rather than in a
  footnote where it would be missed.

- **The container count is measured, the memory figure is not.** The core stack
  is 21 services, counted from `docker-compose.yml` and
  `docker-compose.extended.yml`. OpenMetadata's 6 GiB / 4 vCPU is quoted from
  `NG-0.3`'s own recorded external constraint, not measured here — and under the
  freshness rule that premise is itself due for re-verification when `NG-0.3` is
  promoted.

- **An ADR carries more institutional weight than a recommendation deserves.**
  ADR-0001 and ADR-0002 decide platform behaviour; this one decides a preference.
  The asymmetry is stated in the ADR's own risks section rather than left for a
  reader to notice.

## Deliberately not done

- **`NG-0.9` was not started**, despite this change concluding it should be
  first. That is precisely the failure the `Backlog ordering is not chained
  authorisation` requirement forbids, and this change is the first opportunity to
  either honour it or breach it.
- No `Authorised` cell was flipped. All fourteen remain `no`.
- The register's row order was not changed to match the recommended order. The
  register records dependency; the ADR records preference; conflating them would
  destroy the distinction this programme was restructured around.
- The two recorded contradictions (`NG-1.1`, `NG-1.2`) were not resolved.
- No spec delta was added, and no existing requirement was restated.
- Neither ADR-0001 nor ADR-0002 was amended.
