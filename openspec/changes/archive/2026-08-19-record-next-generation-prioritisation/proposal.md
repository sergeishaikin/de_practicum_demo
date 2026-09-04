## Authorisation

Authorised by the operator on 2026-08-19, conditioned on
`add-next-generation-backlog` being archived first. That condition is satisfied:
it archived as `2026-08-19-add-next-generation-backlog` with zero active changes
remaining.

**This authorisation covers this change and nothing else.** In particular it
does not authorise `NG-0.9`, despite this change recommending `NG-0.9` first,
and it does not authorise any other NG item.

## Why

`add-next-generation-backlog` established fourteen specified items and proved
their ordering is a valid execution order. That answers what *may* start. It
does not answer what *should*, and conflating the two is the mistake the
register most invites: its row order is a dependency layering, and read as a
queue it puts the cheapest, fastest-decaying item ninth.

An unrecorded prioritisation gets re-derived — differently — each time the
question is asked, and an autonomous agent has nothing but the numbering to go
on. So the view is recorded once, with its reasoning and its expiry conditions.

An ADR rather than a change's `design.md`, because the content makes
**programme-level** decisions that outlive any single item: `NG-0.9` ahead of its
number, a fail-fast preflight before the OpenMetadata build, `NG-2.1`+`NG-2.2`
preferred over the Flink branch, and a paper gate for Pinot. Burying those in one
technical change's design would hide decisions that bind thirteen other items.

## What Changes

- `docs/adr/0003-next-generation-backlog-prioritisation.md` — new. Ranking axes,
  a per-item assessment, the recommended wave order and priority bands, the four
  programme-level decisions with their reasoning, a parallelism policy, the
  recommended delivery path, consequences, non-goals, and the conditions that
  would reopen it.
- The ADR opens with a normative statement that **priority is not
  authorisation**, and that reordering the programme requires an explicit
  amendment rather than silent drift.

Documentation only. No runtime behaviour changes, no new dependencies, no
backlog edits.

**Scope fence, checkable rather than descriptive.**

Allowed: `docs/adr/0003-*.md` and this change's own artifacts.

Forbidden, and checkable as such:

- `git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ tests/ scripts/ .planning/`
  SHALL be clean. No Compose, `pyproject.toml`, `uv.lock` or CI workflow edit.
- `git diff --exit-code openspec/backlog/ openspec/specs/` SHALL be clean. This
  change records a view *about* the backlog; it does not edit the backlog, does
  not flip an `Authorised` cell, and does not change the register's row order.
- `git diff --exit-code docs/adr/0001-incremental-silver-and-gold.md docs/adr/0002-steady-state-shadow-policy.md`
  SHALL be clean. Neither existing ADR is amended.
- No NG item is started. `NG-0.9` in particular is not started, despite this
  change arguing it should be first — which is the precise failure mode the
  `engineering-governance` requirement on chained authorisation forbids.
- Work stops when this change is archived.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The rules this ADR obeys — priority is not authorisation, ordering does
not chain, premises are revalidated at promotion — were all ratified by
`add-next-generation-backlog`. This change exercises them; it does not extend
them. Adding a requirement here would restate an existing rule in a second,
driftable form.

## Impact

- `docs/adr/0003-next-generation-backlog-prioritisation.md` — new.
- `openspec/backlog/**` — deliberately untouched.
- `openspec/specs/**` — deliberately untouched.
- Runtime, `tests/`, CI, dependencies and `.planning/` — deliberately untouched.
