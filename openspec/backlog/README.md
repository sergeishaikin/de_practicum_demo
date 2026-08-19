# Backlog

Work that is recorded but not authorised.

## What lives here

`openspec/` has three surfaces and they mean different things:

| Directory | Meaning |
|---|---|
| `openspec/specs/` | Standing capabilities. What is true of the repository now. |
| `openspec/changes/` | Proposals in flight. Each one is authorised, scoped and being executed or archived. |
| `openspec/backlog/` | Future work, recorded so it is not re-derived. **Nothing here is authorised.** |

A backlog item is a specification of work that has been thought through far
enough to be picked up later without re-deriving it, and deliberately not far
enough to start. It states scope, non-goals, requirements, acceptance evidence,
rollback and hard stops. It does not schedule anything.

## Rules

- A backlog item **does not authorise execution.** Starting the work means
  opening the OpenSpec change named in the item's index row, and that requires
  the operator's explicit authorisation, per `openspec/specs/engineering-governance/spec.md`.
- A backlog item is **not evidence.** It describes intended future state in
  `SHALL` form. No claim in it may be cited as something the repository does.
- A backlog item is **not a plan.** It has no task list and no wave ordering.
  Those are produced in `tasks.md` when the change is opened.
- Backlog items are **not a queue in the `.planning/` sense.** `.planning/` is
  the frozen GSD execution record and is not resumed; this directory is a
  forward record and is not executed in place.

## Current backlogs

- [`next-generation/`](next-generation/00-INDEX.md) — the NG-0.1 … NG-2.2
  package: platform provenance, lineage, catalog, OTel/Tempo/Loki, correlation
  and SLOs, data reliability, static typing, Flink, ClickHouse, Pinot, MLflow
  governance and an evaluated incident agent. Start at the index; it carries the
  execution order, the dependency graph, the cross-cutting invariants and the
  status/authorisation table.
