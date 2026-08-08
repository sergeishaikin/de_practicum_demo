# Rejected, deferred and reclassified findings

Companion to `architecture-audit-report.md`. Records what the adversarial challenge pass changed
and why, so that nothing is silently dropped and no severity is quietly averaged.

- **Rejected outright:** 0
- **Reclassified (severity retained, standing changed):** 4
- **Deferred (valid, out of the critical path):** 4
- **Disagreements preserved rather than resolved:** 1

Every finding here survives with its evidence chain intact. "Deferred" means *not part of this
change*, never *not true*.

---

## Rejected outright

**None.** No finding failed the evidence-chain test. Every record in the three specialist files
carried at least one direct or derived item with a location, and none was evidence-free.

This is worth stating plainly rather than treating as a good sign: it partly reflects that the
audit wrote its own findings under a strict contract, not that the findings are beyond challenge.
Each carries `falsePositiveConditions` naming what would disprove it, and those conditions are the
right place to attack them.

---

## Preserved disagreement — not averaged

### F-303 · severity is conditional on Decision 1

| Phase | Position | Basis |
|---|---|---|
| 03 boundaries | **high** — live regression path | `when_matched_update_all` takes no predicate; a lower `kafka_offset` overwrites a higher one |
| 07 data & integration | **currently unreachable** | The producer never repeats an `order_id`, so a replayed duplicate carries identical values and the "regression" rewrites the same data |

**Both are correct under their own domain assumption.** Averaging them to medium would destroy the
information that matters.

**Resolution — recorded as a conditional:**

- Under **D-1-A** (immutable event): structural severity **high**, effective severity **low**. The
  mechanism is broken; the data that would expose it does not exist.
- Under **D-1-B** (mutable entity): **blocker**.

This disagreement is the single clearest piece of evidence that D-1 must be settled before D-3.
It was not a reviewer error in either phase — it is the domain ambiguity of RC-1 surfacing as a
severity conflict.

---

## Reclassified — severity retained, impact class changed

### F-703 · Landing→Bronze has no commit contract

**Challenge:** in a single-host demo stack, executor and driver failures may never occur, so
orphan files may never appear.

**Resolution:** severity **high** retained, confidence **medium** retained. Impact reclassified to
*hypothetical in current operation, structural in design*. **Not observed** — no live stack was
started and no orphan file was found. The confidence level already encodes this; the reclassification
makes it explicit rather than letting a high severity imply an active incident.

### F-301 · Bronze snapshot history has two owners

**Challenge:** `restart: unless-stopped` means recovery normally completes in seconds, far inside
the one-hour retention horizon.

**Resolution:** severity retained; impact reclassified to *hypothetical under normal operation*.
The finding is about **co-ownership of one piece of state by two components with no reconciling
rule**. The narrow window is a mitigating fact, not a refutation — and the window is a property of
current configuration, not of the design.

### F-306 · the only internal import edge is built at runtime

**Challenge:** the fitness function plan chose data-plane guards over import-plane guards, so a
missing import graph blocks nothing that is actually planned.

**Resolution:** the finding stands as a **correction to a discovery-phase claim** — the graph is not
empty because the units have no import coupling, but because the one edge is constructed by
`sys.path` mutation. Its *actionable* content reduces to **record the limitation**. No packaging
change is recommended. Remediation priority: bottom.

### F-702 · single hot partition

**Challenge:** if the exercise intends to demonstrate correctness rather than work reduction, one
partition is not a defect.

**Resolution:** **high** retained. QAS-001 does not say which is intended, and with no work-volume
measure anywhere the question cannot be answered either way. Reframed from "a data defect" to **a
measurement gap with a decision procedure attached** — the scan-volume guard settles it empirically.

---

## Deferred — valid, outside the critical path

### F-1009 · coverage gate covers one of three trees

Adjacent to the declared scope rather than inside it. The `--cov=iceberg` gate leaves `spark/` and
`dags/` unmeasured, and between them they hold the second dedup implementation, the silent-drop
filter and the snapshot expiry. **Lowest priority of the medium findings.** Recommendation stands:
extend the ratchet, do not raise the number.

### F-709 · Postgres truncate-and-rebuild

Out of the medallion critical path, negligible at demo volume, atomic within its transaction.
Retained as **pattern evidence for IR-002** — the same full-overwrite-instead-of-progress-state
move, in a second store — and as a candidate teaching exercise. Not remediation work.

### F-308 · writer and medallion share one image

A defensible simplification for a single-host teaching stack. Deferred as an **accepted-design
candidate**, which requires an explicit decision to accept rather than silent inheritance. It
becomes relevant only if the incremental work is staged such that the writer must stay pinned
while the medallion changes.

### F-705 · silent drop and `failOnDataLoss: false`

Not deferred as unimportant — it is explicitly sequenced. A progress marker that can advance past
silently dropped data is worse than no progress marker, because the loss becomes permanent instead
of repaired by the next full rebuild. **It must be closed before progress state is introduced, not
after**, which places it inside D-2's work rather than as an independent item.

---

## Findings that survived challenge unchanged

`F-302 · F-304 · F-305 · F-307 · F-309 · F-701 · F-704 · F-706 · F-707 · F-708 · F-1001 · F-1002 ·
F-1003 · F-1004 · F-1005 · F-1006 · F-1007 · F-1008 · F-1010`

Each was tested against its own `falsePositiveConditions`. Two are worth noting for the strength
of their evidence:

- **F-704** (no incremental scan in pinned pyiceberg) — verified by direct API introspection against
  the installed 0.11.1, matching `iceberg/Dockerfile:3`. Not an inference.
- **F-1010** (existing test assets are strong) — a *strength* finding, held to the same evidence
  standard as the defects, per the synthesis contract.

---

## What would overturn the synthesis

Stated so the report can be attacked rather than merely believed.

| Discovery | Consequence |
|---|---|
| A declared rule stating orders are immutable facts | RC-1 collapses; D-1 resolves to A; F-303 and F-708 drop to low; C becomes the clear choice |
| A generator change emitting real status transitions | D-1 resolves to B; F-303 becomes a blocker; the D-3 ranking inverts toward B |
| A historical seed loading Bronze across multiple dates | F-702 dissolves; the scan-volume guard passes immediately; C's efficiency objection disappears |
| Spark's file sink proven not to leave orphans in this configuration | F-703 drops to low; RC-3 reduces to F-301 alone |
| A pyiceberg upgrade adding an incremental append scan | Option A returns to contention; F-704 retires |
| Moving the medallion to Spark or Trino | F-701, F-704 and much of D-2 change shape entirely — engine-native change tracking removes the provenance problem |

The last row is the largest unexamined alternative in this audit. It was out of scope because the
profile fixed the medallion as a pyiceberg process, and it is recorded here rather than buried:
**a runtime change would make several of these findings irrelevant, and was never evaluated.**
