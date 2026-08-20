## Authorisation

Authorised by the operator on 2026-08-19, with instruction to execute
autonomously to Definition of Done.

```text
AUTHORISED:      reconcile-next-generation-hard-dependencies

NOT AUTHORISED:  add-static-typing-gate
                 every other NG backlog item
```

## Why

`add-static-typing-gate` was about to be authorised and could not start: the
register declared `NG-0.1` a hard dependency of `NG-0.9`, while ADR-0003 —
written by the same hand, hours later — recommended running `NG-0.9` first. Both
documents validated. Nothing checked them against each other.

Investigating that one contradiction showed it was not one. Four items carried
dependencies that are not technical prerequisites at all, inherited from how the
source package narrated its layers rather than from anything the items consume:

| Item | Declared | Actually consumes |
|---|---|---|
| NG-0.9 | NG-0.1 | nothing — no identity, dataset name, envelope or label |
| NG-1.1 | NG-0.1 … NG-0.7, NG-0.9 | NG-0.1, NG-0.2, NG-0.4 |
| NG-1.2 | NG-0.1, NG-0.4 … NG-0.9 | NG-0.1 |
| NG-2.1 | NG-0.1, NG-0.3 … NG-0.9 | NG-0.1 |

And one item was gated too *weakly*: `NG-2.2` reached `NG-0.3`, `NG-0.5`,
`NG-0.6`, `NG-0.7` and `NG-0.8` only transitively, through `NG-2.1`'s over-broad
list. Trimming that list without noticing would have silently un-gated the agent
from every tool it reads.

Two of these were already recorded as open contradictions (`NG-1.1`, `NG-1.2`)
and were waiting for their implementing change to reach them. Correcting them
here — before any of the four is authorised — is what the governance requires:
the change that finds a contradiction must not be the one that settles it.

## What Changes

- **Register**: the `Depends on` column reconciled against all fourteen item
  bodies. Five rows change. The column's meaning is stated explicitly — a
  technical prerequisite, not a preference — and everything weaker moves to a
  *Soft preferences, not gates* section.
- **Five item bodies**: `NG-0.9`, `NG-1.1`, `NG-1.2`, `NG-2.1`, `NG-2.2`, each
  now separating hard from not-gating and recording why the change was made.
- **Register layering**: recomputed. `NG-0.9` moves to layer 0, `NG-1.2` and
  `NG-2.1` to layer 1, `NG-1.1` to layer 2, `NG-1.3` to layer 3, `NG-2.2` to
  layer 5. Six layers become six, but the shape changes materially: the Flink
  and ClickHouse branches detach from the long pole.
- **Register pointer**: names its recommended-ordering document, so the ordering
  check has something to resolve.
- **ADR-0003**: **no recommendation changed.** The corrected model permits the
  order it already advised. Its derived facts are restated — the layering block
  and the *Blocks* column — its ordering block is normalised so every execution
  slot is a bare item id, and an amendment note records what happened. One of its
  own reopen conditions fired and is marked as such.
- **`validate_backlog.py`**: a new cross-document check. It resolves the ordering
  document the register names and fails if that ordering places an item before a
  hard dependency, omits an item, or lists one twice.
- **`tests/test_backlog_validator.py`**: eight tests over synthetic registers,
  plus one `architecture`-marked test asserting the live register and the live
  ADR agree.
- **`engineering-governance`**: two requirements — what may be recorded as a hard
  dependency, and that a published ordering is machine-checked against the graph.

## Capabilities

### Modified Capabilities

- `engineering-governance`: the existing requirements make a register
  structurally checkable and stop an implementing change that finds a
  contradiction. Neither says what may be *recorded* as a dependency, and neither
  reaches a second document — which is precisely where this contradiction lived.
  Both gaps are closed by the checks this change adds, so the rule and its
  enforcement land together.

## Impact

- `openspec/backlog/next-generation/00-INDEX.md` — column, prose, layering,
  ordering pointer.
- Five `NG-*.md` item bodies.
- `openspec/backlog/validate_backlog.py` — ordering check.
- `tests/test_backlog_validator.py` — new.
- `docs/adr/0003-next-generation-backlog-prioritisation.md` — derived facts and
  block format only.
- `openspec/specs/engineering-governance/spec.md` — two added requirements.

**Scope fence, checkable rather than descriptive:**

- `git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ scripts/ .planning/ docker-compose.yml docker-compose.extended.yml pyproject.toml uv.lock .github/`
  SHALL be clean.
- No NG item is implemented. No type checker is pinned, no mypy or Pyright
  configuration is added, no annotation is written, no OTel, OpenLineage or
  provenance code is touched.
- No `Authorised` cell changes. All fourteen still read `no` at archive.
- Row order in the register is not reordered, and no ADR **recommendation** is
  changed — only facts derived from the register.
- Work stops when this change is archived.
