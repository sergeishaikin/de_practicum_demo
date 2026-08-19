## Authorisation

Authorised by the operator on 2026-08-19. **This authorisation covers this change
and nothing else.**

```text
AUTHORISED:      add-next-generation-backlog

NOT AUTHORISED:  NG-0.1  NG-0.2  NG-0.3  NG-0.4  NG-0.5  NG-0.6  NG-0.7
                 NG-0.8  NG-0.9  NG-1.1  NG-1.2  NG-1.3  NG-2.1  NG-2.2
```

The first draft of this change was written and applied before that authorisation
existed, and was then described as "nothing is authorised" while sitting in
`openspec/changes/`. Those two statements cannot both hold: a change in
`changes/` is by definition in flight. The intended claim was that no *NG item*
was authorised. The authorisation above resolves the governance state
retroactively and explicitly, and the wording is corrected here rather than left
to be inferred.

## Why

An analysis of this branch produced a fourteen-item programme for the next
generation of the platform — provenance identity, OpenLineage, OpenMetadata,
OTel Collector, Tempo, Loki, Grafana correlation and SLOs, unified data
reliability, a static type checker, Flink, ClickHouse, Pinot, MLflow governance
and an evaluated incident agent. The analysis exists; the repository has nowhere
to put it.

`openspec/` currently has two surfaces. `specs/` states what is true now.
`changes/` holds proposals in flight, and `engineering-governance` requires
every change to be authorised individually, with authorisation never carrying
to the next one. Fourteen future items fit neither: recorded as fourteen
changes they would read as fourteen authorisations, and recorded nowhere they
would be re-derived from scratch — differently — the next time the question
comes up.

`.planning/` is not the answer either. It is the frozen GSD execution record,
and the governance spec is explicit that it is historical evidence and not a
work queue.

So this change adds the missing third surface and lands the package in it, with
the governing requirements needed so that a directory of `SHALL` statements about
unbuilt systems cannot later be mistaken for an authorisation, for a description
of the platform, or for a licence to chain one item into the next.

## What Changes

- A new `openspec/backlog/` surface, with a `README.md` that states what a
  backlog item is, what it is not, and how it differs from `specs/`, `changes/`
  and `.planning/`.
- The NG package under `openspec/backlog/next-generation/`: `00-INDEX.md` plus
  fourteen item files, `NG-0.1` through `NG-2.2`, each carrying its own scope,
  non-goals, requirements, acceptance gates, rollback and hard stops.
- A single canonical **register** in the index — replacing what were two
  overlapping tables — with column contracts that make it parseable: item id,
  file, gate (`ADOPT` | `EXPERIMENT`), hard dependencies as item ids, the
  pre-assigned OpenSpec change id, and an `Authorised` cell reading `no` for all
  fourteen. Row order is the execution order and must stay topologically valid.
- A dependency **layering derived from the register** rather than drawn beside
  it, replacing the hand-made ASCII graph that could disagree with the table.
- `openspec/backlog/validate_backlog.py` — an executable structural check over
  every register: unique item ids, unique change ids, resolvable dependencies,
  acyclic graph, row order valid as an execution order, authorisation cells
  constrained to `no` or a date, referenced item files present and still
  declaring themselves unauthorised.
- A **Freshness of external assumptions** section in each of the fourteen items:
  versions, compatibility matrices, resource requirements and connector
  capabilities are assumptions captured on a date and SHALL be re-verified
  against primary documentation at promotion.
- A **promotion contract** in the backlog README: authorisation → pre-assigned
  change id → revalidate repository state and external premises → proposal,
  design, tasks, spec delta → apply → evidence → archive → stop.
- Five requirements in the `engineering-governance` spec: recorded future work
  belongs in the backlog and authorises nothing; **backlog ordering is not
  chained authorisation**; backlog premises are revalidated at promotion; a
  register is structurally checkable; and a backlog contradiction stops the
  implementing change rather than being decided inside its design.
- Pointers in `AGENTS.md` (Planning methodology) and `CLAUDE.md` (Working
  rules), which are the two files that tell a reader where planning lives.

Planning artifacts plus one standalone validation script. No runtime behaviour
changes.

**Scope fence, checkable rather than descriptive.**

Allowed: `openspec/backlog/**`, `openspec/specs/engineering-governance/**`,
`AGENTS.md`, `CLAUDE.md`, and this change's own artifacts.

Forbidden, and checkable as such:

- `git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ tests/ scripts/`
  SHALL be clean at the end of this change. Nothing executable in the platform
  is touched.
- No `docker-compose*.yml`, `pyproject.toml`, `uv.lock` or CI workflow is
  edited. None of the fourteen items is started, including NG-0.9, whose
  type-checker dependency is the cheapest to add and therefore the most
  tempting.
- No file under `.planning/` is edited. This change does not restate the frozen
  GSD record and does not touch the open `04-09` / BENCH-01 obligation.
- No backlog item is copied into `openspec/changes/` as a proposal.
- Every `Authorised` cell reads `no` when this change is archived.
- Work stops when this change is archived. Authorising NG-0.1 is a separate
  decision, and completing this change does not make it.

`tests/` is inside the forbidden set, which is why the structural checker ships
as a standalone script under `openspec/backlog/` rather than as a pytest
architecture fitness test. Wiring it into the suite is deferred to its own
change — see design.md.

## Capabilities

### New Capabilities

None. The backlog surface is a planning artifact, not a platform capability.

### Modified Capabilities

- `engineering-governance`: adds five requirements covering
  recorded-but-unauthorised work. The existing requirements say new work is
  proposed as a change and that authorisation is explicit per change; none of
  them says where work lives before it is proposed, that a completed dependency
  confers nothing on its dependents, that a recorded premise expires, that a
  register must be checkable rather than merely drawn, or that a
  self-contradicting backlog stops the change that finds it rather than being
  reinterpreted inside that change's design. Those five gaps are what a backlog
  introduces, so they are closed in the same change that introduces it. Adding the surface without the rules would create a directory of `SHALL`
  statements with nothing to stop a later reader — or an autonomous agent —
  treating them as authorised, current, or self-chaining.

## Impact

- `openspec/backlog/README.md` — new, including the promotion contract.
- `openspec/backlog/validate_backlog.py` — new, standalone structural check.
- `openspec/backlog/next-generation/00-INDEX.md` and fourteen `NG-*.md` — new.
- `openspec/specs/engineering-governance/spec.md` — five added requirements.
- `AGENTS.md`, `CLAUDE.md` — one pointer each.
- Runtime, `tests/`, CI, dependencies and `.planning/` — deliberately untouched.
