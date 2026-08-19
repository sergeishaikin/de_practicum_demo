# Backlog

Work that is recorded but not authorised.

## What lives here

The repository has four planning surfaces and they mean different things:

| Directory | Meaning |
|---|---|
| `openspec/specs/` | Standing capabilities. What is true of the repository now. |
| `openspec/changes/` | Proposals in flight. Each one is authorised, scoped and being executed or archived. |
| `openspec/backlog/` | Future work, recorded so it is not re-derived. **Nothing here is authorised.** |
| `.planning/` | The frozen GSD execution record for Phases 1–4. Historical evidence; never resumed. |

A backlog item is a specification of work that has been thought through far
enough to be picked up later without re-deriving it, and deliberately not far
enough to start. It states scope, non-goals, requirements, acceptance evidence,
rollback and hard stops. It does not schedule anything.

## Rules

- A backlog item **does not authorise execution.** Starting the work means
  opening the OpenSpec change named in the item's register row, and that requires
  the operator's explicit authorisation, per `openspec/specs/engineering-governance/spec.md`.
- **Ordering is not chained authorisation.** Completing an item does not
  authorise the items that depend on it; it makes them *eligible*. Execution
  stops at the end of every authorised change, including when exactly one
  successor is obvious.
- A backlog item is **not evidence.** It describes intended future state in
  `SHALL` form. No claim in it may be cited as something the repository does.
- A backlog item's **external premises expire.** Versions, compatibility
  matrices, resource requirements and connector capabilities are assumptions
  captured on a date. Every item carries a *Freshness of external assumptions*
  section requiring re-verification at promotion.
- A backlog item is **not a plan.** It has no task list and no wave ordering.
  Those are produced in `tasks.md` when the change is opened.
- Backlog items are **not a queue in the `.planning/` sense.** `.planning/` is
  the frozen GSD execution record and is not resumed; this directory is a
  forward record and is not executed in place.

## Promotion contract

```text
backlog item
     |  explicit operator authorisation  (per item, never inherited)
     v
open exactly the pre-assigned change id from the register
     |
     v
revalidate current repository state
revalidate external premises against primary documentation
     |
     v
proposal -> design -> tasks -> spec delta
     |
     v
apply -> evidence -> archive
     |
     v
STOP.  The next item needs its own authorisation.
```

## Structural check

The register is machine-checked, not merely drawn:

```bash
uv run --locked python openspec/backlog/validate_backlog.py
```

It asserts unique item ids, unique change ids, resolvable dependencies, an
acyclic graph, row order that is a valid execution order, an authorisation cell
that is `no` or a date, and item files that still declare themselves
unauthorised. It also recomputes the dependency layering the register publishes,
so a drawing that disagrees with the table fails.

> **Not yet wired into `pytest`.** This change's scope fence forbids `tests/`, so
> the checker is executable but not gated by CI. Promoting it to an
> `architecture`-marked fitness test alongside the existing M5 gates is deferred
> to its own change.

## Current backlogs

- [`next-generation/`](next-generation/00-INDEX.md) — the NG-0.1 … NG-2.2
  package: platform provenance, lineage, catalog, OTel/Tempo/Loki, correlation
  and SLOs, data reliability, static typing, Flink, ClickHouse, Pinot, MLflow
  governance and an evaluated incident agent. Start at the index; it carries the
  execution order, the dependency graph, the cross-cutting invariants and the
  status/authorisation table.
