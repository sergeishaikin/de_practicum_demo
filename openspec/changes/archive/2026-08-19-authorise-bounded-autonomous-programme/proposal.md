## Authorisation

Authorised by the operator on 2026-08-19, explicitly superseding the
one-change-at-a-time rule **for one bounded programme**.

```text
AUTHORISED:  this change, and the Next Generation ADOPT programme it records

COVERED:     backlog items whose canonical Gate is ADOPT, taken in ADR-0003
             priority order constrained by the hard-dependency DAG,
             each as its own OpenSpec change

NOT COVERED: EXPERIMENT items (NG-1.1, NG-1.2, NG-1.3, NG-2.2)
             any newly invented work
             any change to the rules bounding the programme
```

## Why

The programme cannot legally start. `engineering-governance` currently says, in
force:

> Work SHALL stop at the end of each authorised change and wait for a separate
> authorisation … an agent that has just satisfied an item's dependencies has
> thereby produced eligibility, not permission … THEN the agent reports
> completion and stops.

That was ratified this morning, and it is stricter than the programme the
operator has now authorised. Proceeding without recording the supersession would
leave the repository's standing contract saying one thing while a series of
archived changes did another — and the requirement most obviously violated would
be the one about autonomous agents not continuing on their own.

Recording it also captures what the operator's authorisation *limits*, which chat
does not preserve: what the programme covers, what it never covers, and what
still stops it.

## What Changes

- **Two requirements modified.** `Authorisation is explicit and per change` and
  `Backlog ordering is not chained authorisation` gain one carve-out each, so the
  spec is internally consistent rather than silently contradicted.
- **Two requirements added.** What a bounded programme authorisation must state
  to exist at all — a closed membership rule, what it excludes, what ends it —
  and that a programme never authorises its own extension.
- Each programme item still runs as its own change with its own fence, gates and
  archive. A programme authorises the *sequence*, not a merge.

Documentation and governance only.

**Scope fence:**

- `git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ scripts/ tests/ .planning/ docker-compose.yml docker-compose.extended.yml pyproject.toml uv.lock .github/`
  SHALL be clean.
- `openspec/backlog/**` unchanged — this records how work is authorised, not what
  the work is. No `Authorised` cell moves.
- No NG item is implemented. `add-static-typing-gate` is not begun in this
  change.

## Capabilities

### Modified Capabilities

- `engineering-governance`: the per-change rule and the no-chaining rule each
  gain the single stated exception; two requirements are added defining what a
  bounded programme authorisation must contain and forbidding a programme from
  widening itself. Without the first pair the spec contradicts the authorised
  mode of work; without the second pair the exception would have no boundary,
  which is the failure the original rule existed to prevent.

## Impact

- `openspec/specs/engineering-governance/spec.md` — two modified, two added.
- Runtime, tests, CI, dependencies, `.planning/`, `openspec/backlog/` — untouched.
