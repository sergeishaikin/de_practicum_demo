## Authorisation

Explicit ancillary authorisation inside the bounded Next Generation programme,
granted 2026-08-20 as governance-support work. Not an NG item and not added to
the register. NG-0.2 resumes automatically on archive.

## Why

`openspec/backlog/next-generation/` was written as a pure backlog: fourteen
items, none authorised, none started. That is no longer what it is. NG-0.9 and
NG-0.1 are complete and archived, NG-0.2 is in flight, and eleven remain
planned — but every artifact still described the original state.

Three concrete failures followed:

- **The register could not represent completion.** Its own prose said a row
  "records the change's disposition once the change is archived" while the table
  had no state or disposition column, so the lifecycle it described was
  unrepresentable.
- **The validator enforced a false invariant.** `REQUIRED_ITEM_MARKERS` demanded
  that *every* item file declare `**Status:** PROPOSED` and
  `**Execution authorization:** NONE`, including the two that had shipped. The
  checker was actively keeping completed work misdescribed.
- **Two governance documents disagreed.** `backlog/README.md` said execution
  stops after every change and each successor needs a new authorisation;
  `engineering-governance` had since gained the bounded-programme exception that
  the programme is currently running under.

The sharpest risk is not tidiness. A `DONE` item's body describes the platform
*before* that item landed — NG-0.1's says the platform has identifiers but no
contract binding them — and an agent reading it as current state re-solves a
solved problem.

## What Changes

- **The register gains a lifecycle.** `State` (`PLANNED` / `ACTIVE` / `DONE` /
  `STOPPED`) and `Disposition` (`pending` / `ADOPTED` / `DO_NOT_ADOPT`) are
  separate columns, because a completed experiment concluding `DO_NOT_ADOPT` is
  a success. `Authorised` splits into the **grant** and its date, so programme
  membership is distinguishable from a per-item operator authorisation.
- **Each item file declares its own lifecycle.** Technical bodies are untouched;
  only the header block changes. `DONE` files carry an explicit warning that
  they are historical intent rather than current behaviour.
- **The validator checks the register against the repository.** `ACTIVE` implies
  a change directory, `DONE` implies exactly one complete archive and no active
  directory, `PLANNED` implies neither; dependencies must be settled before a
  dependent starts; the file's header must match its row.
- **`REQUIRED_ITEM_MARKERS` loses the false invariant** and keeps only the
  freshness section, which matters *more* after completion, not less.
- **`backlog/README.md`** records bounded-programme authorisation, the lifecycle,
  and that completed items are historical intent.
- **`tests/test_backlog_lifecycle.py`** — 16 `architecture` tests, including a
  negative case for each way the register can lie, and the live register checked
  against the live repository. The checker was previously not wired into pytest
  at all.

**Scope fence:**

- **No NG item is re-specified.** The technical body of all fourteen files —
  scope, product decision, non-goals, requirements, acceptance evidence, failure
  injection, rollback, hard stops — is unchanged. History is not rewritten to
  match implementation.
- No change to what any item requires, to the dependency graph, or to ADR-0003's
  ordering.
- No production code. `git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/
  observability/ scripts/ .planning/ docker-compose*.yml pyproject.toml uv.lock
  .github/` SHALL be clean.
- The directory is **not** moved. `backlog/` → `programmes/` would churn every
  validator, ADR and cross-reference in the middle of NG-0.2; the semantic
  correction lands first and the move stays available as later cleanup.

## Capabilities

### Modified Capabilities

None. `engineering-governance` already carries the bounded-programme
authorisation and the backlog rules; this change makes the register and its
checker consistent with what that spec already says, and adds no new rule.

## Impact

- `openspec/backlog/next-generation/00-INDEX.md` — lifecycle columns.
- All fourteen `NG-*.md` — header block only.
- `openspec/backlog/validate_backlog.py` — lifecycle checks.
- `openspec/backlog/README.md` — programme authorisation and lifecycle.
- `tests/test_backlog_lifecycle.py` — new.
