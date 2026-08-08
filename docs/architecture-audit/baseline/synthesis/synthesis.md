# Architecture audit — synthesis

- **Repository revision:** `d20b2062` (branch `feature/extended-local-stack`)
- **Scope:** only architecture bearing on moving Silver and Gold from full-overwrite to
  incremental processing. **This is not a full architecture review and must not be read as one.**
- **Phases run:** 01 discovery · 02 intent · 03 dependency boundaries · 07 data & integration ·
  10 testability & evolution · 11 synthesis.
  **Deliberately not run:** clean/hexagonal, modularity & SOLID, DDD, security, quality attributes.
- **Findings:** 28 (10 high, 14 medium, 2 low, 2 info) from three specialist files, merged by
  `aak merge` with **no fingerprint collisions**. `aak validate report` valid.
- **Conformance score:** suppressed — zero ADRs, all nine declared rules reconstructed from one
  prose document.
- **Risk index 100.0:** saturated arithmetic over a deliberately narrow, high-intensity audit of
  one change surface. **Not a quality grade. Not comparable to anything. Do not cite it.**

---

## Executive summary

The question the audit was asked — *how do we make Silver incremental* — turned out to be too
narrow to answer. It resolves into **four independent architectural decisions plus one
prerequisite defect that is not a decision at all**.

The highest risk in the project is not the merge strategy.

> **Three artifacts in this repository describe three different domain models, and none of them
> is authoritative.**

Everything else — which merge primitive, where progress lives, whether Gold changes — inherits
its risk profile from that unresolved question.

---

## Five root causes

The 28 findings are manifestations of five causes. Findings are **linked** to causes, never
duplicated; each is counted once in the totals.

### RC-1 · No single source of truth for the domain model
`F-1001 · F-708 · F-303 · F-304` → **Decision 1** · impact: **current**

Three artifacts answer "what does a repeated `order_id` mean" differently:

| Artifact | Says | Evidence |
|---|---|---|
| The producer | **Immutable event** — fresh `uuid4` per event, no order_id ever recurs | `orders_producer.py:59` |
| The e2e fixture | **Mutable entity** — publishes one order_id twice with different payloads, asserts the later wins | `test_lakehouse_e2e.py:118` |
| The Postgres serving schema | **Mutable entity** — `order_id` PRIMARY KEY, `on conflict do update set customer, amount, country, status` | `orders_streaming.py:179` |

Two of three say mutable. The dissenting one is the one that generates the live data.

The third artifact is new in synthesis: a `PRIMARY KEY` with an `UPDATE` of business attributes
on conflict is a **DDL-level declaration that an order mutates**. It is the most formal statement
of domain semantics anywhere in the repository, and it contradicts the generator.

### RC-2 · Progress state is a responsibility no component holds
`F-701 · F-301 · F-707 · F-305` → **Decision 2** · impact: **structural**

Bronze has no row-level provenance — ten columns, none recording when or by which load a row
arrived. No delta is derivable from the data at all. The three units keep three mutually
invisible progress models; the medallion keeps none. The one existing progress artifact is
unbounded and non-atomically written.

### RC-3 · Bronze was never established as a trustworthy log
`F-703 · F-301 · F-705` → **Prerequisite 1** · impact: **hypothetical in operation, structural in design**

The Landing→Bronze boundary has no commit contract: a five-second mtime heuristic stands in for
Spark's commit manifest, and the `/_temporary/` guard is aimed at the wrong protocol. Bronze can
separately gain duplicates from writer re-append. **Neither is detectable today because the full
rebuild silently absorbs both.**

### RC-4 · Full overwrite is load-bearing for three properties, not one
`F-302 · F-303 · F-301 · F-709` → **Decisions 3 and 4** · impact: **structural**

IR-002 is confirmed and understated. Full overwrite substitutes for progress state, *and* for the
ordering semantics of AR-004, *and* for a silver→gold edge that does not exist. It is also
repairing RC-3's duplicates on every cycle.

### RC-5 · No architectural rule in this system is executable
`F-309 · F-1002…F-1008 · F-306 · F-1009` → cross-cutting · impact: **current**

Sixty tests, all behavioural. No ownership, direction, retention, ordering or reconciliation
assertion anywhere. Import-plane guards unavailable. No live-stack test blocks a PR. Every
fixture single-partition.

---

## Decision 1 · Domain model

> **What does a repeated `order_id` mean?**

**Status: OPEN — blocks Decision 3.**

| | **A · Immutable event** | **B · Mutable business entity** |
|---|---|---|
| A repeat is | a replay | an order update |
| AR-004 is | transport-level duplicate defence | a business projection rule |
| F-303 | largely dissolves — replay carries identical values | **becomes a blocker** |
| F-708 invariant | holds by construction | cannot be assumed |
| Silver becomes | a derived view | a stateful business projection |
| Natural fit | changed-partition rebuild (C) | business-key approaches (B) rise sharply |
| Requires fixing | the e2e fixture's naming | **the generator** |

**The audit does not choose.** It records that the evidence is 2:1 for the mutable reading, that
the dissenting artifact is the live data source, and that this decision **changes the ranking of
Decision 3**.

Choosing a merge strategy before this is choosing under an unstated assumption about the domain.

---

## Decision 2 · Progress ownership

> **Bronze snapshot ids, Kafka offsets, a control table, or a writer-published outbox?**

**Eliminated on evidence:**

- **Kafka offsets** — per-partition monotonic only; two hops behind by the time data reaches Bronze.
- **A row-level watermark on existing columns** — F-701: no such column exists.

**Viable, with their real costs:**

| Option | Cost |
|---|---|
| Bronze snapshot ids | Inherits F-301's retention dependency **and** F-704's missing incremental scan; requires hand-rolled manifest diffing on library internals |
| Medallion control table | Depends on nothing the medallion does not own — but F-305: `marts` has five DDL owners, three issuing runtime DDL, one a student exercise, all on one credential |
| **Writer-published outbox** | The writer already holds the information in memory at append time |

**Audit position:** the outbox is the only option that *removes* a cross-component ownership
conflict rather than adding one. That is an argument from ownership, not from performance.

**Hard constraint:** whatever is chosen must be atomically written and bounded. The one existing
precedent (F-707) is neither, and must not be copied.

---

## Decision 3 · Silver execution model

**Status: OPEN — depends on D-1 and D-2.**

**Eliminated:**

- **A · snapshot-delta** — F-704: the pinned pyiceberg has no incremental scan. Requires rebuilding
  one from `inspect` metadata, on internals, on top of snapshots F-301 lets maintenance delete.
- **D · changelog/CDC** — a fourth persisted layer and a fourth schema declaration in a system that
  already fails to keep three in sync. No consumer needs row-level change events.

**Not an alternative:** **E · control table** is the missing component *every* option needs. It is
Decision 2.

**Live options:**

| | Strengths | Costs |
|---|---|---|
| **B** upsert | Immune to F-702. Correct under D-1-B | Cannot express latest-offset-wins; needs explicit `join_cols`; no partition pruning; delta must be pre-deduplicated |
| **C** changed-partition | Only APIs present in 0.11.1. **F-303 dissolves rather than needing mitigation.** Idempotent by construction | Rests on F-708's unstated invariant; reduces no work until F-702 is fixed |
| **F** hybrid | C + outbox; makes the silver→gold read real; removes F-301 from the medallion's critical path | Requires F-702 and F-708 resolved; largest surface |

**The critical dependency:** *B and C fail in opposite conditions.* C is correct and cheap but
demonstrates nothing until F-702 is fixed. B is insensitive to F-702 but carries every constraint
in F-303. **If F-702 is not addressed, the ranking inverts.**

**Audit position:** **F is the strongest candidate on the evidence gathered, and its principal
merit is not performance.** It is that the rebuild of a changed scope remains deterministic and
idempotent — the same property that makes the current full overwrite correct. The audit stops
short of ratifying it because D-1 is unresolved and D-1-B would materially strengthen B.

---

## Decision 4 · Gold

> **Should Gold be incremental?**

**Audit position: no. Rebuild it in full from persisted Silver, every cycle.**

- `count_distinct` and `mean` do not compose from a delta
- Gold is one row per `event_date × country × status` — tens of rows at demo scale
- The silver→gold edge must be created regardless; a full rebuild creates it as a side effect
- Gold is unpartitioned, so any scoped rewrite rewrites the whole table anyway
- Incremental would need sketch state (HLL or equivalent) to guard tens of rows
- **A full rebuild is exactly verifiable; an incremental aggregate with sketches is approximately
  verifiable**

Recorded explicitly because "incremental Silver *and* Gold" is the intuitive framing and the
evidence contradicts it. The phase is more accurately:

```
Scoped-rebuild Silver
  +
Persisted Silver → deterministic full Gold rebuild
```

---

## Prerequisite 1 · The Bronze commit contract

**Not a decision.** F-703 exists independently of the incremental question and would remain after
any of the six options ships. It concerns whether Bronze is a trustworthy log at all.

It can and should proceed **in parallel** with D-1…D-4.

Smallest guard: extract file eligibility from `list_new_files` into a pure function — *given a
listing and the set of committed paths, return the eligible files* — and test it on the PR tier.

---

## F-702 needs a guard, not a decision

**The scan-volume fitness function is the decision procedure.**

`DataScan.plan_files()` makes files-per-cycle observable with no instrumentation. Write the guard
first, then attempt to build a fixture that makes it pass. If none can exist, F-702 has answered
itself and either the generator or the partition grain must change.

This avoids both failure modes: choosing an architecture to fit an artificially simple generator,
and choosing a data shape to fit a preferred architecture.

---

## Adversarial challenge

Every finding was re-tested against its strongest alternative explanation and against whether its
impact is **current** or **hypothetical**. Eight findings changed standing.

**The one that matters most — F-303, and a genuine disagreement between phases:**

Phase 3 rated it high on a live regression path. Phase 7 then found the producer never repeats an
`order_id`, so a replayed duplicate carries identical values and the regression rewrites the same
data. **Both are correct under their own domain assumption.**

Resolution: **severity is conditional on D-1, recorded as a conditional and not averaged to
medium.** Under D-1-A the mechanism is broken but unreachable — structural severity high,
effective severity low. Under D-1-B it is a blocker.

This is the clearest evidence in the whole audit that D-1 must be settled first.

Other outcomes: F-703 and F-301 retain severity with impact reclassified as hypothetical in
current operation; F-306's actionable content reduces to *record the limitation* since the plan
chose data-plane guards; F-1009, F-709 and F-308 deferred. Full list in
`rejected-or-deferred-findings.md`.

**Double-counting check:** 28 in, 28 out, no fingerprint collisions. Semantic overlaps (F-301
under RC-2 *and* RC-3; F-303 under RC-1 *and* RC-4) are linked, not merged.

---

## Strengths — evidence-backed

Recorded so remediation does not treat this as greenfield.

- **Real fault injection through production seams** — `test_crash_recovery.py` starts the writer as
  a real subprocess, kills it via `os._exit`, asserts the exact exit code, restarts, verifies no
  duplicate append. Isolated namespaces, full cleanup. *The direct template for the medallion
  crash suite D-2 requires.*
- **A deterministic e2e with exact expected values** — 100 events, 98 landed, 95 silver rows,
  3 duplicates removed, 7 violations, 90.0 UK delivered, unique Bronze load-ids. *Rare in a demo
  repository, and the reason this change can be validated at all.*
- **The writer's idempotency design is sound in isolation** — load-id in snapshot summary,
  pending/done state, bounded commit-conflict retry with table reload. *F-301 is a cross-component
  ownership defect, not a defect in the writer's logic.*
- **A zero-cost migration seam already exists and is unused** — all medallion table identifiers are
  environment variables. *A shadow Silver needs no code change.*
- **Three-tier CI with a coverage ratchet** — the structure to hang fitness functions on exists;
  only the trigger tier and the guard content are missing.

---

## Recommended next step

**Do not start writing incremental code.**

The audit has assembled enough evidence for a real architecture decision record rather than one
written from intuition. The natural next artifact is a design document with:

1. Current architecture · 2. Constraints (F-301…F-1010) · 3. Decision matrix · 4. Chosen
architecture · 5. Migration strategy · 6. Fitness functions · 7. Shadow rollout · 8. Rollback

Two things should be settled inside it, in this order: **D-1 first** (it re-ranks D-3), then D-2.
D-4 is effectively decided by the evidence. PREREQ-1 proceeds in parallel.

This would also be **the repository's first ADR**. Every declared rule in this audit was
reconstructed from prose because none exists — which is itself the most durable finding here.

---

## Coverage and limitations

- **Declared rules evaluated:** 7 of 9. **ADRs:** 0.
- **Boundary model:** data-plane and infrastructure-plane, not import-plane.
- **Not observed:** no live stack was started in any phase; no test executed; no CI run triggered;
  no orphan file, commit conflict, duplicate append or concurrency window reproduced. Spark
  file-sink semantics are documented behaviour, not measured. pyiceberg introspected locally at
  0.11.1 (matching the image pin), not inside the container.
- **Out-of-state phases:** 07, 10 and 11. `audit.state.json` enforces the standard order and would
  have required clean/hexagonal, SOLID and DDD first — all outside the declared scope. State
  remains at revision 3, complete 3/13.
- **No compliance claim is issued.** Five specialist audits were not run; absence of a finding is
  not evidence of absence.
- **D-1 is unresolved and D-3's ranking is conditional on it.** The audit position on D-3 is
  provisional for that reason.

---

## Handoff

This report is the **read-only baseline** for `plan-architecture-remediation` and for any later
`verify-architecture-remediation` run. Its digest must be recorded before remediation begins;
verification compares against it.
