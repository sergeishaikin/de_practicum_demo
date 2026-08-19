# ADR-0003 — Next-generation backlog prioritisation

| | |
|---|---|
| **Status** | **Accepted** — a recommended scheduling strategy for the NG programme. It schedules nothing and authorises nothing; every item still requires its own per-change authorisation |
| **Date** | 2026-08-19 |
| **Deciders** | *(unassigned)* |
| **Supersedes** | nothing. It is the first programme-level scheduling decision for the NG backlog, which until now carried only a dependency-ordered register |
| **Evidence base** | [`openspec/backlog/next-generation/00-INDEX.md`](../../openspec/backlog/next-generation/00-INDEX.md) — the register and its machine-checked layering; [`openspec/backlog/validate_backlog.py`](../../openspec/backlog/validate_backlog.py); the compose service inventory in `docker-compose.yml` and `docker-compose.extended.yml`; `pyproject.toml` |

Related: [ADR-0001](0001-incremental-silver-and-gold.md) and
[ADR-0002](0002-steady-state-shadow-policy.md) decide the current medallion
model. This ADR does not touch either; it concerns work that has not started.

---

## Normative statement, first

**Priority is not authorisation.**

This ADR establishes a recommended scheduling strategy only.

Completing a prerequisite makes a dependent backlog item eligible for
consideration; it SHALL NOT authorise that item. Every NG item still requires
explicit per-change authorisation under `engineering-governance`.

**This ADR does not authorise NG-0.9**, despite recommending it first, and does
not authorise any other item.

The priority order MAY change when implementation evidence invalidates its
assumptions. Such a change requires an explicit amendment to this ADR; agents
and contributors SHALL NOT silently reorder the programme.

---

## Context

### The question

The register in `00-INDEX.md` orders fourteen items `NG-0.1` … `NG-2.2` and
proves the ordering is a valid execution order. That answers *what may start*.
It does not answer *what should start*, and the two are not the same: the
register's row order is a dependency layering, and reading it as a queue is the
most available mistake it invites.

### Why it is a question now

The backlog was established and archived on 2026-08-19
(`add-next-generation-backlog`). Fourteen specified items now exist with no
recorded view of which of them earns attention first. Left unrecorded, that view
gets re-derived — differently — every time someone asks, and an autonomous agent
has nothing but the numbering to go on.

### What the numbering actually encodes

`NG-0.9` is numbered ninth because of where it sat in the source package's
narrative, not because it is ninth in value. The register's own machine-computed
layering places it in **layer 0**, alongside `NG-0.1`, with no hard dependency at
all:

```text
layer 0   NG-0.1, NG-0.9
layer 1   NG-0.2, NG-0.4, NG-1.2, NG-2.1
layer 2   NG-0.3, NG-0.5, NG-0.6, NG-1.1
layer 3   NG-0.7, NG-1.3
layer 4   NG-0.8
layer 5   NG-2.2
```

> **Amended 2026-08-19** by `reconcile-next-generation-hard-dependencies`. As
> first written, this ADR recommended `NG-0.9` before `NG-0.1` while the register
> declared `NG-0.1` a hard dependency of it — a contradiction this document
> created and did not notice. The reconciliation established that four items
> carried inherited layering conventions rather than technical prerequisites, and
> that `NG-0.9` has none. **No recommendation below was changed**: the corrected
> dependency model permits the order this ADR already advised. The layering above
> and the *Blocks* column are restated from the corrected register; the reasoning
> is untouched.

---

## Decision

### Ranking axes

Four axes, independent — an item may be high on one and low on another:

| Axis | Question |
|---|---|
| **Blocking power** | How many items cannot start until this lands? |
| **Cost** | Relative build effort, S → XL. Not calendar time. |
| **Risk** | Probability it fails, stalls, or forces rework elsewhere. |
| **Decay** | Does delaying it get *more* expensive over time? |

Decay is the axis that reorders this programme, and the one most often skipped.

### Item assessment

| Item | Blocks | Cost | Risk | Decay | Placement |
|---|---|---|---|---|---|
| NG-0.1 provenance contract | 0.2, 0.4, 1.2, 2.1 and all telemetry naming | M | Low | **High** | Wave 1 |
| NG-0.9 typing gate | nothing | **S** | Low | **Highest** | Wave 1 |
| NG-0.2 OpenLineage | 0.3, 1.1 | L | Med — Spark listener compatibility | Med | Wave 2 |
| NG-0.4 OTel Collector | 0.5, 0.6, 1.1 | M | Low | Med | Wave 2 |
| NG-0.3 OpenMetadata | 0.7, 0.8, 2.2 | **XL** | **High** — resources and connector coverage | Low | Wave 3 |
| NG-0.5 Tempo | 0.7, 2.2 | S/M | Low | Low | Wave 3 |
| NG-0.6 Loki | 0.7, 2.2 | M | Low | Med — the cost is structured logging, not Loki | Wave 3 |
| NG-0.7 correlation / SLO | 0.8, 2.2 | M | Low | Low | Wave 4 |
| NG-0.8 data reliability | 2.2 | M | Low | Low | Wave 5 |
| NG-2.1 MLflow | 2.2 | M | Low | Low | Wave 6A |
| NG-2.2 incident agent | nothing | L | Med — plus recurring provider cost | Low | Wave 6A |
| NG-1.1 Flink | 1.3 | **XL** | **High** — version matrix | Low | Wave 6B |
| NG-1.2 ClickHouse | 1.3 | L | Med | Low | Wave 6B |
| NG-1.3 Pinot | nothing | L/XL | **Highest** — may have no use case at all | Low | Conditional |

### Recommended programme order

```text
Stage 0 - paper gate, not an execution slot:
  evaluate whether a distinct application-serving query corpus exists
  -> if none can be defined: DO NOT IMPLEMENT Pinot

Wave 1:
  NG-0.9
  NG-0.1

Wave 2:
  NG-0.2
  NG-0.4

Wave 3:
  NG-0.3
  NG-0.5
  NG-0.6

Wave 4:
  NG-0.7

Wave 5:
  NG-0.8

Wave 6A - preferred:
  NG-2.1
  NG-2.2

Wave 6B - alternative:
  NG-1.1
  NG-1.2

Last, conditional:
  NG-1.3
```

Every execution slot above is a bare item id on its own line, and
`validate_backlog.py` parses them in order and fails if any item appears before
one of its hard dependencies. Annotations therefore live here rather than in the
block: Wave 2's two items may be developed concurrently but are verified
separately; Wave 3's NG-0.3 opens with OM-PREFLIGHT, below; and Wave 6A's two
items are one product slice delivered as two bounded changes. Stage 0 is a
decision, not a slot, so it names no bare id.

Summarised as priority bands:

| Priority | Work |
|---|---|
| **P0** | `NG-0.9` → `NG-0.1` |
| **P0 — long pole** | `NG-0.2` → OM-PREFLIGHT → `NG-0.3` |
| **P1 — parallel branch** | `NG-0.4` → `NG-0.5` + `NG-0.6` |
| **P1 — first payoff** | `NG-0.7` → `NG-0.8` |
| **P2 — preferred differentiator** | `NG-2.1` + `NG-2.2` |
| **P2 — alternative technical branch** | `NG-1.1` → `NG-1.2` |
| **P3 — conditional** | `NG-1.3`, paper gate first |

---

## The four decisions this ADR actually makes

### 1. NG-0.9 runs first, ahead of its number

`NG-0.9` pins a type checker, declares typed scope and adds a CI gate. No new
service, no runtime change; the cheapest item in the package. Every item after it
writes new Python — lineage emitters, OTel instrumentation, metadata adapters,
agent tools, scorers. Landing it ninth means retro-typing all of that; landing it
first makes it nearly free. Its value decays monotonically, which is exactly the
property the numbering fails to express.

Secondary reason: `NG-0.9` owns `pyproject.toml`, `uv.lock` and CI ordering.
`NG-0.2` adds an OpenLineage dependency and `NG-0.4` an OTel SDK. First means one
lock rewrite instead of a three-way collision.

`NG-0.9` and `NG-0.1` SHOULD be sequenced rather than run concurrently. Both are
small; serialising two small items removes all file conflict for almost no cost.

### 2. NG-0.3 begins with a bounded preflight, not a full build

`NG-0.3` is simultaneously the most expensive item, the most resource-hungry,
and the one whose failure mode is worst: its own spec names DataHub as the
fallback, so an unmet connector assumption means redoing an XL item.

`add-openmetadata-catalog` SHALL therefore open with a fail-fast gate before any
expensive integration work:

```text
OM-PREFLIGHT

prove against the pinned candidate version:
  Airflow coverage
  dbt artifacts
  Kafka metadata
  Trino / Iceberg visibility
  required lineage edges
  required column-lineage subset
  OpenLineage ingestion
  resource envelope

PASS -> continue full OpenMetadata implementation
FAIL -> stop before expensive integration
        classify the gap
        evaluate DataHub only if the blocker is material
```

This is deliberately **not** a new backlog item. It is the first bounded gate
inside `add-openmetadata-catalog`, so the backlog does not grow an entry for
every risk-reduction step.

### 3. NG-2.1 + NG-2.2 are one product slice, delivered as two changes

`NG-2.1`'s own product decision forbids installing MLflow before a real ML/agent
use case exists. Scheduling the two into distant waves would violate that
rationale while appearing to respect the register. They remain **two bounded
OpenSpec changes** — the governance boundary is unchanged — but they are
scheduled as one slice and authorised in close succession or not at all.

### 4. The AI branch is preferred over the streaming branch

`NG-1.x` and `NG-2.x` are independent subtrees; neither blocks the other. The
choice between them is real, and this ADR recommends `NG-2.1` + `NG-2.2` first:

| | Streaming branch (6B) | AI branch (6A) |
|---|---|---|
| Proves | Stateful event-time streaming, checkpoint recovery, parity under crash | Evaluated agent: golden set, holdout, immutable baseline, deterministic scorers |
| Risk | Version-matrix risk, **precedented in this repository** — Spark 4.2 has no Iceberg runtime JAR, which is why the PyIceberg bridge exists | Eval-quality risk, recurring provider cost, and a data-egress decision |
| Cost | XL + L | M + L |
| Rarity | Common senior-DE credential | Rare — most agent work carries no offline evaluation at all |

The AI branch consumes investment already made in `NG-0.3` and `NG-0.5`–`0.8`
rather than opening a new front, is cheaper, and demonstrates the scarcer
capability. The streaming branch's risk profile matches a failure this repository
has already hit once.

This is a recommendation, not a foreclosure: `NG-1.1` remains fully specified and
its gate remains `EXPERIMENT`.

---

## Parallelism policy

Two ceilings, routinely conflated. They bind differently, and the second binds
harder.

### Authoring concurrency

Permitted **only when file ownership is explicitly disjoint.**

| Pair | Verdict |
|---|---|
| `NG-0.1` ∥ `NG-0.9` | Clean but low payoff — serialise |
| `NG-0.2` ∥ `NG-0.4` | ⚠ Both edit `iceberg/writer/iceberg_writer.py` and `iceberg/medallion/iceberg_medallion.py` — split by service or accept a rebase |
| `NG-0.5` ∥ `NG-0.6` | Acceptable — overlap limited to Collector config and Grafana datasource provisioning |
| `NG-0.3` ∥ `{NG-0.5, NG-0.6}` | **Best pair in the programme** — disjoint file trees and disjoint profiles |
| `NG-1.x` ∥ `NG-2.x` | Fully disjoint |

### Live profile concurrency

**Default: one heavy optional profile at a time.**

The core stack is already 21 containers — Postgres, Airflow, MinIO, three Spark
services, Jupyter, Kafka and its UI, the Iceberg REST catalog, writer and
medallion, the observability exporter, Prometheus, Grafana, Trino, Metabase, the
producer, the streaming job, and Superset with its MCP sidecar. `NG-0.3`'s own
recorded constraint puts OpenMetadata at 6 GiB and 4 vCPU before OpenSearch;
`NG-1.3` adds four more components.

Therefore:

- There SHALL be no combined `core + metadata + flink + pinot + ml` mega-stack
  acceptance test.
- Each profile is verified as `core + exactly that capability`, producing its own
  measured clean-stack receipt.
- Two items sharing a dependency layer may still be impossible to verify
  simultaneously. **Parallelism in this programme is bounded by memory, not by
  the dependency graph.**

This is recorded as policy precisely because the layering makes the opposite
mistake attractive: a reader who sees five items in independent subtrees may
conclude that five agents can bring five profiles up at once.

No measured profile receipt exists yet — `NG-0.1` requires them and none of the
profiles has been built. Every cost figure in this ADR is relative, not measured.

---

## Recommended path to the first differentiated end-state

```text
NG-0.9 -> NG-0.1 -> NG-0.2 -> NG-0.3 -> NG-0.7 -> NG-0.8 -> NG-2.1 -> NG-2.2
   S        M         L        XL        M         M         M         L
```

This is deliberately **not** called "the critical path". The programme has no
single mathematical critical path, because it can legitimately end in several
different states: `NG-1.3` may terminate in `DO NOT IMPLEMENT`, the `NG-1.x` and
`NG-2.x` subtrees are an either/or/both fork, and any `EXPERIMENT` item may end
in `REMOVE / DO NOT ADOPT` — which the register's invariant 10 records as a
successful outcome. What is written above is the current preferred delivery path
to one chosen end-state, and it changes if that choice changes.

---

## Consequences

- The register's row order and this ADR's recommended order are **different
  things**, and both are now recorded. The register proves what *may* start; this
  ADR recommends what *should*. Neither grants permission.
- `add-openmetadata-catalog` acquires an obligation before it is ever authorised:
  it opens with OM-PREFLIGHT.
- `NG-1.3` acquires a cheap decision point that can remove an XL item from the
  programme before any implementation work: its own spec already states that
  `DO NOT IMPLEMENT` is the correct outcome when no distinct
  application-serving workload can be defined.
- Profile-concurrency policy constrains how acceptance evidence is produced for
  every heavy item.

## Non-goals

- This ADR does not evaluate the technology choices. Whether OpenMetadata beats
  DataHub is decided in `add-openmetadata-catalog`, on evidence.
- It assigns no dates, owners or capacity.
- It produces no `tasks.md` for any item; task lists belong to authorised
  changes.
- It does not resolve the two recorded contradictions in the register (`NG-1.1`,
  `NG-1.2`). Those stop the change that reaches them, per
  `engineering-governance`.
- It does not amend `ADR-0001` or `ADR-0002`.

## What would reopen this

Any of the following invalidates a premise and requires an amendment rather than
silent reordering:

- OM-PREFLIGHT fails, making `NG-0.3` materially more expensive or forcing the
  DataHub fallback — the long pole changes, and with it the recommended order.
- `NG-1.3`'s paper gate succeeds with a genuine application-serving workload,
  raising Pinot above conditional.
- The AI branch's provider cost or data-egress constraints prove unacceptable,
  making the streaming branch the preferred one.
- Measured profile receipts show the resource ceiling is materially different
  from the estimate above, changing what can be verified concurrently.
- ~~A dependency contradiction resolves in a direction that changes the
  layering — for example `NG-1.1` being confirmed as *not* gated on `NG-0.3`,
  which would detach the Flink branch from the long pole.~~
  **This condition fired on 2026-08-19.** `NG-1.1` was confirmed as *not* gated
  on `NG-0.3`, and the Flink branch is detached from the long pole: it now sits
  in layer 2 rather than layer 4. `NG-1.2` and `NG-2.1` moved to layer 1 for the
  same reason. The recommendation was re-examined and **kept**: Wave 6A and 6B
  are late by preference — cost, risk and what each demonstrates — not because
  the graph forced them there, and the graph never was what placed them.
  A future contradiction resolving the same way remains a reopen condition.
