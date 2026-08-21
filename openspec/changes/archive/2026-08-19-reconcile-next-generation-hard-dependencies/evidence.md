# Evidence — reconcile-next-generation-hard-dependencies

Executed 2026-08-19 on `test/dbt-extensive-testing`. Commit `2e31c41`.

Authorised by the operator on 2026-08-19 with instruction to execute
autonomously to Definition of Done.

## The analysis, all fourteen items

The test applied to every declared edge: *can this item be designed, implemented,
and its acceptance evidence produced without the dependency existing?*

### Edges kept — a technical prerequisite in each case

| Item | Kept | Because |
|---|---|---|
| NG-0.2 | NG-0.1 | Its own scenario requires event names to use "the canonical dataset naming contract from NG-0.1" |
| NG-0.3 | NG-0.1, NG-0.2 | Runtime lineage "SHALL arrive through the supported OpenMetadata OpenLineage endpoint"; asset identities use the naming contract |
| NG-0.4 | NG-0.1 | "OTel attributes SHALL map to NG-0.1 identities without duplicating incompatible names" |
| NG-0.5, NG-0.6 | NG-0.4 | The Collector is the only normal write path |
| NG-0.7 | NG-0.3, NG-0.4, NG-0.5, NG-0.6 | Provisions Tempo and Loki datasources; deep-links to catalog entities |
| NG-0.8 | NG-0.3, NG-0.7 | Lineage must be navigable in the catalog; failures must reach trace and logs |
| NG-1.3 | NG-1.1, NG-1.2 | Flink for keyed repartitioning and FF-14; ClickHouse to compare against |

### Edges removed — not technical prerequisites

| Item | Removed | Because |
|---|---|---|
| **NG-0.9** | NG-0.1 | Nothing in it consumes an identity, dataset name, provenance envelope or telemetry label. Its architecture-fitness requirement lists future rules as *examples*, and those live in the index invariants, not in NG-0.1's deliverables |
| **NG-1.1** | NG-0.3, NG-0.5, NG-0.6, NG-0.7, NG-0.9 | NG-0.3 is called "recommended" in the item's own next sentence. Parity, the failure matrix and resource measurement need no catalog, trace store, log store or correlation layer. NG-0.9 imposes typed scope on later items rather than being needed by them |
| **NG-1.2** | NG-0.4 – NG-0.9 | Nothing blocks a Kafka projection and a benchmark. The item's own acceptance gates qualify the catalog and Grafana links with "where available" |
| **NG-2.1** | NG-0.3 – NG-0.9 | MLflow's evaluation, prompt and model governance needs no catalog, trace backend, log backend, correlation layer or reliability model; it carries its own `ml` profile and its own tracing |

### Edges added — the opposite failure

| Item | Added | Because |
|---|---|---|
| **NG-2.2** | NG-0.3, NG-0.5, NG-0.6, NG-0.7, NG-0.8 | Every one is a tool the agent reads. One acceptance scenario turns on Tempo/Loki being *unavailable* while the data plane is healthy, which requires them to exist. These were named in the item body but reached the register only transitively through NG-2.1's over-broad list |

**Ordering mattered.** NG-2.2's five dependencies were recorded *before* NG-2.1
was trimmed, so the graph was never briefly wrong.

**Transitive-but-true edges were kept**, not reduced — NG-0.7 keeps NG-0.4 though
NG-0.5 implies it. Removing redundant edges is a different act from removing
false ones, and mixing them would make the diff unreviewable for correctness.

## Resulting layering

Recomputed by the validator, not by hand:

```text
layer 0   NG-0.1, NG-0.9
layer 1   NG-0.2, NG-0.4, NG-1.2, NG-2.1
layer 2   NG-0.3, NG-0.5, NG-0.6, NG-1.1
layer 3   NG-0.7, NG-1.3
layer 4   NG-0.8
layer 5   NG-2.2
```

Row order in the register was **not** changed and remains a valid execution
order.

## ADR-0003

Checked against the corrected graph **before** editing: every wave already
respects the real dependencies, so **no recommendation was changed**. The
corrected model permits the `NG-0.9` → `NG-0.1` order it already advised, both
now being layer 0.

Restated, as derived facts only: the layering block, the *Blocks* column. The
order block was normalised so every execution slot is a bare item id, with its
annotations moved to prose directly below. An amendment note records what changed
and what did not.

One of the ADR's own reopen conditions fired and is marked as such: *"NG-1.1
being confirmed as not gated on NG-0.3, which would detach the Flink branch from
the long pole."* It was, and it did — NG-1.1 moves from layer 4 to layer 2. The
recommendation was re-examined and kept, because Waves 6A and 6B are late by
cost, risk and what each demonstrates, not because the graph placed them there.

## Live negative proof

Against the **real** register and ADR. Each mutation applied, run, reverted.

| Mutation | Exit | Message |
|---|---|---|
| **The historical defect, reintroduced** — NG-0.9 depends on NG-0.1 while the ADR runs 0.9 first | 1 | `orders NG-0.9 at slot 0 but its hard dependency NG-0.1 at slot 1; an ordering may not place an item before a dependency` |
| NG-0.2 dropped from the ordering | 1 | `item(s) never ordered: ['NG-0.2']` |
| NG-0.7 moved ahead of NG-0.3 | 1 | `orders NG-0.7 at slot 4 but its hard dependency NG-0.3 at slot 5 …` (and NG-0.5) |
| Restored | 0 | `backlog validation OK (14 items)` |

The first row is the point: the exact defect that shipped this morning now fails
by name.

## Regression tests

`tests/test_backlog_validator.py` — eight tests over **synthetic** registers, so
they state the rule rather than an accident of the live files:

- an ordering consistent with the graph passes, with the expected layering;
- an ordering that inverts a hard dependency fails;
- an omitted item fails; a duplicated item fails;
- a named-but-missing ordering document fails;
- prose naming an item is **not** an execution slot;
- a register with no ordering pointer skips the check rather than failing it;
- `architecture`-marked: the live register and live ADR agree, and NG-0.9 is
  layer 0.

## Gates

| Check | Result |
|---|---|
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked black --check .` | 77 files unchanged (two files formatted first, then re-verified) |
| `uv run --locked pytest tests --cov=iceberg --cov-fail-under=90` | **417 passed**, 70 deselected, coverage **94.29%** |
| Test delta | 409 → 417, exactly the eight added tests |
| Coverage delta | none — `iceberg/` untouched |
| `validate_backlog.py` | `backlog validation OK (14 items)` |
| `openspec validate … --strict` | change valid; both standing specs valid |

## Scope fence

```bash
git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ scripts/ \
  .planning/ docker-compose.yml docker-compose.extended.yml pyproject.toml \
  uv.lock .github/ tests/integration/
git diff --exit-code docs/adr/0001-incremental-silver-and-gold.md \
  docs/adr/0002-steady-state-shadow-policy.md
```

Both exit 0. All fourteen `Authorised` cells still read `no`.

## Live CI

Reported at handoff for commit `2e31c41`; the archive commit that follows carries
only the spec merge and the change directory move.

## Findings recorded rather than papered over

- **The contradiction was mine.** ADR-0003 and the register were written hours
  apart in the same session, and the ADR's recommendation was never checked
  against the dependency column it had just been derived from. The rule that
  caught it — *Backlog contradictions stop implementation* — was ratified in the
  change immediately before. Its first live application blocked its own author.

- **Two contradictions were already recorded and the pattern was missed.** NG-1.1
  and NG-1.2 had been logged as "unresolved, stricter reading taken as interim".
  Both were instances of one defect, and logging them individually obscured that
  a whole column needed re-deriving.

- **Removing a dependency can be wrong.** The judgement rests on reading each
  item's requirements and acceptance evidence; an item may consume in
  implementation what its specification never mentions. The freshness rule
  already requires premises to be re-verified at promotion, and a change that
  finds it needs a removed prerequisite stops as any contradiction does.

- **The register now depends on a document outside `openspec/`.** Renaming
  ADR-0003 breaks validation until the pointer follows. Accepted: a pointer that
  fails loudly beats an ordering silently unchecked.

## Deliberately not done

- **No NG item implemented.** No type checker pinned, no mypy or Pyright
  configuration, no annotation written, no OTel, OpenLineage or provenance code.
- No `Authorised` cell changed.
- Register rows not reordered.
- No ADR recommendation changed; ADR-0001 and ADR-0002 untouched.
- The dependency graph was not reduced to its transitive reduction.
- `add-static-typing-gate` is now unblocked and remains **unauthorised**.
