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
one governing requirement so that a directory of `SHALL` statements about
unbuilt systems cannot later be mistaken for either an authorisation or a
description of the platform.

## What Changes

- A new `openspec/backlog/` surface, with a `README.md` that states what a
  backlog item is, what it is not, and how it differs from `specs/`, `changes/`
  and `.planning/`.
- The NG package under `openspec/backlog/next-generation/`: `00-INDEX.md` plus
  fourteen item files, `NG-0.1` through `NG-2.2`, each carrying its own scope,
  non-goals, requirements, acceptance gates, rollback and hard stops.
- A status/authorisation table in the index: per item, the decision gate, its
  dependencies, the OpenSpec change id it will open as, and an explicit
  `Authorised` column that reads `no` for all fourteen.
- One added requirement in the `engineering-governance` spec: recorded future
  work belongs in `openspec/backlog/`, and a backlog item does not authorise
  execution.
- Pointers in `AGENTS.md` (Planning methodology) and `CLAUDE.md` (Working
  rules), which are the two files that tell a reader where planning lives.

Documentation and planning only. No runtime behaviour changes.

**Scope fence, checkable rather than descriptive:**

- `git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ tests/ scripts/`
  SHALL be clean at the end of this change. Nothing executable is touched.
- No `docker-compose*.yml`, `pyproject.toml`, lock file or CI workflow is
  edited. None of the fourteen items is started, including NG-0.9, whose
  type-checker dependency is the cheapest to add and therefore the most
  tempting.
- No file under `.planning/` is edited. This change does not restate the frozen
  GSD record and does not touch the open `04-09` / BENCH-01 obligation.
- No backlog item is copied into `openspec/changes/` as a proposal.
- Every `Authorised` cell reads `no` when this change is archived.
- Work stops when this change is archived. Authorising NG-0.1 is a separate
  decision.

## Capabilities

### New Capabilities

None. The backlog surface is a planning artifact, not a platform capability.

### Modified Capabilities

- `engineering-governance`: adds a requirement covering recorded-but-unauthorised
  work. The existing requirements say new work is proposed as a change and that
  authorisation is explicit per change; neither of them says where work lives
  before it is proposed, which is exactly the gap that produced fourteen
  homeless specifications. Adding the surface without the rule would create a
  directory of `SHALL` statements with nothing to stop a later reader treating
  them as authorised, or as describing the platform.

## Impact

- `openspec/backlog/README.md` — new.
- `openspec/backlog/next-generation/00-INDEX.md` and fourteen `NG-*.md` — new.
- `openspec/specs/engineering-governance/spec.md` — one added requirement.
- `AGENTS.md`, `CLAUDE.md` — one pointer each.
- Runtime, tests, CI, dependencies and `.planning/` — deliberately untouched.
