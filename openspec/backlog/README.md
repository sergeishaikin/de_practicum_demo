# Backlog

Work recorded ahead of execution, and — once a programme is running — its
lifecycle state.

## What lives here

The repository has four planning surfaces and they mean different things:

| Directory | Meaning |
|---|---|
| `openspec/specs/` | Standing capabilities. What is true of the repository now. |
| `openspec/changes/` | Proposals in flight. Each one is authorised, scoped and being executed or archived. |
| `openspec/backlog/` | Recorded work and, for a running programme, its lifecycle. A `PLANNED` item is unauthorised; `ACTIVE` and `DONE` rows record work the operator has authorised. |
| `.planning/` | The frozen GSD execution record for Phases 1–4. Historical evidence; never resumed. |

A backlog item is a specification of work that has been thought through far
enough to be picked up later without re-deriving it, and deliberately not far
enough to start. It states scope, non-goals, requirements, acceptance evidence,
rollback and hard stops. It does not schedule anything.

## Rules

- A backlog item **does not authorise execution.** Starting the work means
  opening the OpenSpec change named in the item's register row, and that requires
  the operator's authorisation, per `openspec/specs/engineering-governance/spec.md`.
- **Ordering is not chained authorisation.** Completing an item does not
  authorise the items that depend on it; it makes them *eligible*.
- **Execution stops at the end of every authorised change — unless a bounded
  programme authorisation covers the next item.** `engineering-governance` since
  2026-08-19 permits an operator to authorise a closed, pre-named set of items
  in advance, and the next-generation `ADOPT` items are currently covered by one.
  Within such a programme, execution continues to the next eligible item without
  stopping. A programme authorisation never covers its own extension: an item
  outside the named set still needs its own grant.
- **A row's authorisation records its grant, not only its date.** `none`, or the
  grant it traces to — a per-item operator authorisation or programme membership.
  A bare date cannot distinguish the two, and after the programme existed that
  ambiguity was real.
- A backlog item is **not evidence.** It describes intended future state in
  `SHALL` form. No claim in it may be cited as something the repository does.
- **A completed item is historical intent, not current truth.** A `DONE` item's
  body describes the repository as it was *before* that item landed. NG-0.1's
  body says the platform has identifiers but no contract binding them; that was
  true when it was written and false now. Current behaviour lives in
  `openspec/specs/`, the documentation, the code and the tests. Every `DONE`
  file carries that warning, and the validator requires it.
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
backlog item  (State: PLANNED)
     |  operator authorisation - per item, or membership of a bounded programme
     |  never inherited from a completed predecessor
     v
open exactly the pre-assigned change id from the register   (State: ACTIVE)
     |
     v
revalidate current repository state
revalidate external premises against primary documentation
     |
     v
proposal -> design -> tasks -> spec delta
     |
     v
apply -> evidence -> archive                                (State: DONE)
     |                                             (Disposition: ADOPTED /
     |                                                           DO_NOT_ADOPT)
     v
STOP - unless a bounded programme authorisation already covers the next
item, in which case continue to it and repeat.
```

## Structural check

The register is machine-checked, not merely drawn:

```bash
uv run --locked python openspec/backlog/validate_backlog.py
```

It asserts unique item ids, unique change ids, resolvable dependencies, an
acyclic graph, and row order that is a valid execution order. It also recomputes
the dependency layering the register publishes, so a drawing that disagrees with
the table fails.

Since the register became lifecycle-aware it additionally checks the register
**against the repository** rather than trusting it:

- an `ACTIVE` row has its change directory under `openspec/changes/`;
- a `DONE` row has exactly one archive, no active directory, and that archive
  carries proposal, design, tasks and evidence;
- a `PLANNED` row has neither;
- nothing that has started is unauthorised, and every grant carries a date;
- no item is `ACTIVE` or `DONE` while a hard dependency is still `PLANNED`;
- each item file's own `**Lifecycle:**` header matches its row, and a `DONE`
  file warns that it is historical intent.

It previously required every item file to declare `PROPOSED` with
`authorization NONE`. That invariant was true when the package was written and
false the moment the first item shipped, so completed work was being forced to
misdescribe itself; it has been replaced by the lifecycle checks above.

Wired into the fast suite as `tests/test_backlog_lifecycle.py`
(`architecture`-marked), so the register is checked on every run rather than
when someone remembers the script.

## Current backlogs

- [`next-generation/`](next-generation/00-INDEX.md) — the NG-0.1 … NG-2.2
  package: platform provenance, lineage, catalog, OTel/Tempo/Loki, correlation
  and SLOs, data reliability, static typing, Flink, ClickHouse, Pinot, MLflow
  governance and an evaluated incident agent. Start at the index; it carries the
  execution order, the dependency graph, the cross-cutting invariants and the
  status/authorisation table.
