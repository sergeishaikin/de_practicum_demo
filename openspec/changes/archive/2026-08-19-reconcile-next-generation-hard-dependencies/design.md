## Context

See proposal.md — Why. Three constraints shape the approach.

**The contradiction was mine, and it was found by the rule rather than by luck.**
`Backlog contradictions stop implementation` was ratified hours earlier and its
first live application blocked a change I was about to start. That is the
mechanism working, and it is also why the correction had to be a separate change
rather than a paragraph in `add-static-typing-gate`'s design.

**One contradiction was a symptom.** NG-0.9 was the case that surfaced, because
an ADR happened to disagree with it out loud. The same defect was present in
three more items and had already been recorded twice as "unresolved" without
anyone noticing the pattern: the dependency column had inherited the source
package's narrative layering.

**A dependency model can be wrong in two directions.** Over-gating is the visible
failure; under-gating is the dangerous one. Trimming NG-2.1's list would have
removed the only path by which NG-2.2 reached the tools it reads.

## Goals / Non-Goals

**Goals:**

- A dependency column that means one thing: technical prerequisite.
- Register and item bodies that cannot disagree.
- A machine check that would have caught the original defect.
- ADR-0003 left factually correct without its reasoning being rewritten.

**Non-Goals:**

- Not implementing NG-0.9 or any item.
- Not reordering the register's rows.
- Not re-deciding ADR-0003's recommendations.
- Not converting the dependency graph to its transitive reduction.

## Decisions

**The test applied to every declared dependency.** *Can this item be designed,
implemented, and its acceptance evidence produced without the dependency
existing?* Applied to all fourteen items, not only the four that changed, so the
ten unchanged rows are a result rather than an omission.

Worked through: `NG-0.2` consumes NG-0.1's canonical dataset naming, which its
own scenario names — kept. `NG-0.4` maps its attributes to NG-0.1 identities —
kept. `NG-0.3` receives runtime lineage through the OpenLineage endpoint — kept.
`NG-0.7` provisions Tempo and Loki datasources and deep-links to catalog entities
— kept. `NG-0.8` needs both the catalog and correlation — kept. `NG-1.3` needs
Flink for keyed repartitioning and ClickHouse to compare against — kept.

`NG-0.9` fails the test outright: nothing in it consumes an identifier, dataset
name, provenance envelope or telemetry label. Its architecture-fitness
requirement lists future rules as *examples*, and those live in the index's
invariants rather than in NG-0.1's deliverables.

**Transitive edges are kept, not reduced.** Removing redundant-but-true edges is
a different act from removing false ones, and mixing them in one change would
make the diff impossible to review for correctness. `NG-0.7` keeps `NG-0.4` even
though `NG-0.5` implies it.

**NG-2.2 gains dependencies, and that ordering mattered.** It reached
`NG-0.3`, `NG-0.5`, `NG-0.6`, `NG-0.7` and `NG-0.8` only through `NG-2.1`'s
over-broad list. They were recorded explicitly *before* that list was trimmed, so
the graph was never briefly wrong. This is the second scenario in the added
requirement, because it is the failure mode a cleanup of this kind invites.

**ADR-0003's ordering was checked, found consistent, and left alone.** The
corrected graph permits `NG-0.9` → `NG-0.1` — both are layer 0 — and every other
wave already respected the real dependencies. Instruction was explicit that an
ADR should not be rewritten without need, and the reasoning behind Waves 6A and
6B never rested on the graph: they are late by cost, risk and what each
demonstrates. Only derived facts were restated, and the amendment note says so,
so a reader can tell a correction from a change of mind.

**The ordering check is a cross-document check, deliberately.** Neither the
register nor the ADR was internally inconsistent. Any check living wholly inside
one of them would have passed. So the register names its ordering document and
the validator resolves it — the pointer lives in the register because the
register is already the single source of truth for the dependency model.

**A slot is a bare item id alone on its line.** An ordering document has to be
able to name an item without scheduling it: ADR-0003's Stage 0 paper-gates
`NG-1.3` and its annotations name others. Requiring a bare id makes commentary
unambiguously non-scheduling, and it is a rule an author can follow without
reading the parser. The block was reformatted to comply, and its annotations
moved to prose immediately below.

**Tests use synthetic registers, plus one on the real one.** A test that only
fails when someone edits the live backlog describes an accident, not a rule. The
synthetic ones state the rule; the `architecture`-marked one pins that the live
register and the live ADR agree, which is the thing that actually regressed.

## Risks / Trade-offs

**Removing a dependency can be wrong.** The judgement rests on reading each
item's requirements and acceptance evidence, and an item may consume something in
implementation that its specification never mentions. The mitigation is the
freshness rule already on every item: premises are re-verified at promotion, and
a change that discovers it needs a removed prerequisite stops, as any contradiction
does. Over-gating was the safer error only if delay is free, and here it blocked
a change outright.

**The register now depends on a document outside `openspec/`.** If ADR-0003 is
renamed, validation fails until the pointer follows. Accepted: a broken pointer
failing loudly is better than an ordering silently unchecked, and it is one line.

**Four items moving earlier in the layering may read as encouragement.** NG-1.2
and NG-2.1 now sit in layer 1. The layering block states it is permissive rather
than prescriptive, and ADR-0003 still schedules both late — but a reader who
takes the graph as advice will be misled, which is the same confusion the
register was restructured to prevent, arriving from the other direction.
