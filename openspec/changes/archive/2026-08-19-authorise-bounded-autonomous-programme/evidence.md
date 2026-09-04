# Evidence — authorise-bounded-autonomous-programme

Executed 2026-08-19 on `test/dbt-extensive-testing`. Commit `154a020`.

## Why this change existed at all

The operator authorised a multi-change programme. `engineering-governance`, as
ratified earlier the same day, forbade it in terms that named this exact
situation: *"an agent that has just satisfied an item's dependencies has thereby
produced eligibility, not permission"* and *"THEN the agent reports completion
and stops"*.

Proceeding without recording the supersession would have left the repository's
standing contract contradicting a series of archived changes, with the violated
requirement being the one about unattended agents continuing on their own.

## What changed

| Requirement | Action |
|---|---|
| Authorisation is explicit and per change | MODIFIED — one named exception, plus a scenario for an authorisation claimed but not recorded |
| Backlog ordering is not chained authorisation | MODIFIED — same exception; eligibility-is-not-permission kept intact |
| A bounded programme authorisation covers a closed, pre-named set | ADDED |
| A programme authorisation never covers its own extension | ADDED |

Modified rather than overridden by a third requirement, so the capability states
one rule rather than two competing ones.

## Checks

| Check | Result |
|---|---|
| `openspec validate … --strict` | change valid; both standing specs valid |
| `validate_backlog.py` | `backlog validation OK (14 items)` |
| Scope fence | clean across runtime, tests, CI, dependencies, `.planning/`, `openspec/backlog/` |
| Python completion gate | not applicable — documentation only, no executable command or configuration example changed |

## Live CI on `154a020`

| Workflow | Conclusion |
|---|---|
| CI | success |
| M5 architecture gates | success |
| S1 dbt semantic lineage | success |
| H1 clean reproducible stack | success |

## Deliberately not done

- No NG item begun in this change; `add-static-typing-gate` is its own change.
- No `Authorised` cell moved here.
- The programme's membership rule was written to be evaluable — `Gate == ADOPT`,
  ADR-0003 order constrained by the DAG — rather than left to judgement.
