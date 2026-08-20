## Verification receipt

Commit under test: `cffdb10`.

| Run | Workflow | Conclusion |
|---|---|---|
| [32355807568](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32355807568) | CI | success |
| [32355807600](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32355807600) | M5 architecture gates | success |
| [32355807564](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32355807564) | S1 dbt semantic lineage | success |
| [32355807524](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32355807524) | H1 clean reproducible stack | success |

Host gate: ruff and black clean, `mypy` clean over 9 files, **497 passed**
(up from 481), coverage **94.65%** — unchanged, correctly: this change adds no
`iceberg/` code.

### The register now describes the repository

```text
backlog validation OK (14 items)
  layer 0: NG-0.1, NG-0.9
  layer 1: NG-0.2, NG-0.4, NG-1.2, NG-2.1
  ...
```

Validating that output means more than it used to. The checker previously
verified only internal consistency — unique ids, resolvable dependencies,
topological row order — all of which can hold while the table is simply false.
It now resolves each row against `openspec/changes/` and
`openspec/changes/archive/`:

| Item | Row says | Resolved to |
|---|---|---|
| NG-0.9 | `DONE` / `ADOPTED` | `archive/2026-08-20-add-static-typing-gate/` |
| NG-0.1 | `DONE` / `ADOPTED` | `archive/2026-08-20-add-platform-provenance-contract/` |
| NG-0.2 | `ACTIVE` | `changes/add-openlineage-runtime-lineage/` |
| 11 others | `PLANNED` | neither directory exists |

### The false invariant, removed

`REQUIRED_ITEM_MARKERS` required every item file to declare
`**Status:** PROPOSED` and `**Execution authorization:** NONE`. Two items had
shipped, so the checker was enforcing a statement it could prove wrong from the
archive beside it. It now requires the freshness marker only — which matters
*more* after completion, since a completed item's premises are the ones a later
reader is most likely to take on trust.

What replaced it is stricter, not looser: each file declares its own
`**Lifecycle:**`, the validator requires it to match the row, and a `DONE` file
must carry the historical-intent warning.

### Negative proof

`tests/test_backlog_lifecycle.py` — 16 `architecture` tests. Each failure mode
has its own case, because a validator nobody has watched fail is a validator
nobody knows works:

```text
DONE without an archive                       caught
DONE with an archive missing evidence.md      caught
ACTIVE without an active change               caught
PLANNED with implementation already underway  caught
a dependent item ACTIVE before its prerequisite   caught
an item file disagreeing with its row         caught
authorisation without a traceable grant       caught
DONE with a pending disposition               caught
PLANNED already recording an outcome          caught
DONE without the historical-intent warning    caught
a truthful register                           passes
a completed EXPERIMENT concluding DO_NOT_ADOPT    passes
```

The last two matter most. The first proves the negatives are not satisfied by a
checker that rejects everything; the second is why `State` and `Disposition` are
separate columns at all — NG-1.3's own body says its correct outcome may be
`DO NOT IMPLEMENT`, and under one column that finished experiment would have to
be recorded as unfinished or as adopted.

The checker was **not wired into pytest at all** before this change; the
previous note deferring that cited a scope fence which no longer applies.

### Item bodies are untouched

The whole diff across all fourteen `NG-*.md` files, excluding blockquote header
lines, is three blank `>` markers — themselves part of the new headers:

```bash
git diff openspec/backlog/next-generation/NG-*.md \
  | grep -E '^[+-]' | grep -v '^[+-][+-]' | grep -vE '^\+> |^-> '
+>
+>
+>
```

No requirement, acceptance criterion, non-goal, rollback or hard stop was
edited. History was not rewritten to match implementation.

### A test file I should have found first

`tests/test_backlog_validator.py` already existed, covering the ordering check
with synthetic registers. The column change broke seven of its tests, and it was
not discovered until the full suite ran. The two files turned out complementary
— ordering there, lifecycle here — so its fixtures were migrated to the
nine-column schema and each file now names the other. Had they overlapped, the
right outcome would have been one file, not two.

### What this does not establish

- **Nothing derives `State` automatically.** The validator rejects disagreement
  between the register and the repository; it does not repair it. A completed
  item whose row is never updated fails validation rather than self-correcting.
- **`ACTIVE` means a directory exists**, not that work is genuinely progressing.
  An abandoned change directory would keep an item looking active; `STOPPED`
  exists for the honest version, and nothing forces its use.
- **State is recorded twice** — in the row and in the file header — and kept
  consistent by a check rather than by having one source.
- **`STOPPED` is unexercised.** No item has been abandoned, so that branch of
  the state machine has fixture coverage only.
