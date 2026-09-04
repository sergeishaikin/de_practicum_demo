# Next-Generation Data Platform — Spec-Driven Delivery Index

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Purpose

This package converts the proposed next-generation platform work into an ordered set of bounded specifications. It deliberately avoids a "technology zoo": a product is adopted only when it delivers a distinct capability, survives failure/recovery tests, preserves the current repository guarantees, and has an explicit rollback path.

The existing platform remains the baseline: Kafka, Spark Structured Streaming, MinIO landing, PyIceberg/Iceberg Bronze-Silver-Gold, Trino, PostgreSQL/dbt/Airflow, Prometheus/Grafana, BDD, architecture gates, and clean-stack verification. New work extends that platform; it does not silently redefine existing ownership.

## Backlog register

This table is the canonical, machine-checked register for the package. It is the
single source of truth for order, dependencies, change ids, lifecycle state,
authorisation provenance and outcome; `validate_backlog.py` in the parent
directory parses it and fails if any of those invariants break — including
against the actual contents of `openspec/changes/` and `openspec/changes/archive/`.

This package is a **programme registry**, not a pure backlog. It began as one:
every item was unauthorised future work. It no longer is — some items are
complete, one is in flight, most are still planned — and the register records
which is which rather than pretending the whole package is still ahead of us.

**A completed item's specification is historical intent, not current truth.**
NG-0.1's body says the platform has identifiers but no contract binding them;
that was true before NG-0.1 and is false now. Current behaviour lives in
`openspec/specs/`, the repository documentation, the code and the tests. Reading
a `DONE` item as a description of the present is how an agent re-solves a solved
problem, which is why the lifecycle header on each file says so explicitly.

Row order is the execution order and SHALL remain topologically valid: an item's
dependencies always appear in earlier rows.

Column contracts, so the register stays parseable:

- **Item** — `NG-<major>.<minor>`, unique.
- **File** — the item specification, in this directory.
- **Gate** — exactly `ADOPT` or `EXPERIMENT`. What kind of decision the item is,
  fixed when the item was written. Never a lifecycle value.
- **Depends on** — comma-separated item ids, or `-` for none. **Hard**
  dependencies only; soft preferences are recorded in the notes below.
- **Change** — the pre-assigned OpenSpec change id, unique across the backlog.
- **State** — `PLANNED`, `ACTIVE`, `DONE` or `STOPPED`. Where the work is.
- **Disposition** — the product outcome. `pending` until the work concludes,
  then `ADOPTED` or `DO_NOT_ADOPT`.
- **Authorised by** — `none`, or the grant the authorisation traces to. A date
  alone records *when* but not *why*, which cannot distinguish a per-item
  operator grant from programme membership.
- **At** — `-`, or the ISO date of that grant.

State and Disposition are separate because a completed experiment that concludes
`DO_NOT_ADOPT` is a success, not a failure. Collapsing them would make the only
honest outcome of NG-1.3's paper gate look like an incomplete item.

```text
PLANNED ──▶ ACTIVE ──▶ DONE
                └────▶ STOPPED
```

| Item | File | Gate | Depends on | Change | State | Disposition | Authorised by | At |
|---|---|---|---|---|---|---|---|---|
| NG-0.1 | `NG-0.1-platform-provenance-contract.md` | ADOPT | - | `add-platform-provenance-contract` | DONE | ADOPTED | `programme:bounded-autonomous-next-generation` | 2026-08-20 |
| NG-0.2 | `NG-0.2-openlineage.md` | ADOPT | NG-0.1 | `add-openlineage-runtime-lineage` | DONE | ADOPTED | `programme:bounded-autonomous-next-generation` | 2026-08-20 |
| NG-0.3 | `NG-0.3-openmetadata.md` | ADOPT | NG-0.1, NG-0.2 | `add-openmetadata-catalog` | DONE | ADOPTED | `programme:bounded-autonomous-next-generation` | 2026-08-20 |
| NG-0.4 | `NG-0.4-opentelemetry-collector.md` | ADOPT | NG-0.1 | `add-opentelemetry-collector` | DONE | ADOPTED | `operator:explicit-ng-0.4-milestone-1` | 2026-08-20 |
| NG-0.5 | `NG-0.5-grafana-tempo.md` | ADOPT | NG-0.4 | `add-tempo-trace-backend` | DONE | ADOPTED | `operator:explicit-ng-0.5-milestone-1` | 2026-09-03 |
| NG-0.6 | `NG-0.6-grafana-loki.md` | ADOPT | NG-0.4 | `add-loki-log-backend` | DONE | ADOPTED | `operator:explicit-ng-0.6-milestone-1` | 2026-09-04 |
| NG-0.7 | `NG-0.7-grafana-correlation.md` | ADOPT | NG-0.3, NG-0.4, NG-0.5, NG-0.6 | `add-grafana-correlation-slo` | PLANNED | pending | `none` | - |
| NG-0.8 | `NG-0.8-data-reliability.md` | ADOPT | NG-0.3, NG-0.7 | `unify-data-reliability` | PLANNED | pending | `none` | - |
| NG-0.9 | `NG-0.9-engineering-quality-gates.md` | ADOPT | - | `add-static-typing-gate` | DONE | ADOPTED | `programme:bounded-autonomous-next-generation` | 2026-08-19 |
| NG-1.1 | `NG-1.1-apache-flink-shadow-streaming.md` | EXPERIMENT | NG-0.1, NG-0.2, NG-0.4 | `evaluate-flink-shadow-streaming` | PLANNED | pending | `none` | - |
| NG-1.2 | `NG-1.2-clickhouse-hot-analytics.md` | EXPERIMENT | NG-0.1 | `evaluate-clickhouse-hot-analytics` | PLANNED | pending | `none` | - |
| NG-1.3 | `NG-1.3-apache-pinot-realtime-serving.md` | EXPERIMENT | NG-1.1, NG-1.2 | `evaluate-pinot-realtime-serving` | PLANNED | pending | `none` | - |
| NG-2.1 | `NG-2.1-mlflow-ai-governance.md` | ADOPT | NG-0.1 | `add-mlflow-ai-governance` | PLANNED | pending | `none` | - |
| NG-2.2 | `NG-2.2-data-platform-incident-agent.md` | EXPERIMENT | NG-0.3, NG-0.5, NG-0.6, NG-0.7, NG-0.8, NG-2.1 | `evaluate-data-platform-incident-agent` | PLANNED | pending | `none` | - |

A row is edited only to record something that has actually happened elsewhere.
`State` moves only with the OpenSpec change it names: to `ACTIVE` when that
change directory exists, to `DONE` when it is archived, to `STOPPED` when the
work is abandoned with a recorded reason. `Disposition` is set when the work
concludes. A row SHALL NOT be edited to look like progress that the change
record does not carry — and the validator now checks exactly that against
`openspec/changes/` and `openspec/changes/archive/` rather than trusting the
table.

### What the `Depends on` column means

A hard dependency is a **technical prerequisite**: the dependent item cannot be
designed, implemented, or have its acceptance evidence produced until it exists.
Anything weaker — a preference, a recommendation, a sensible order, a rule that
applies only once the other item exists — is not a dependency and is recorded
below instead.

The column was reconciled against all fourteen item bodies on 2026-08-19 in
`reconcile-next-generation-hard-dependencies`. Before that it carried inherited
layering conventions, which made the register disagree with the recommended
ordering in ADR-0003 and over-gated four items.

### Soft preferences, not gates

- **NG-0.9 SHOULD be done early**, and ADR-0003 recommends it first. Its cost
  rises as more Python is added. That is scheduling, not gating: nothing in
  NG-0.9 consumes an identity, dataset name, provenance envelope or telemetry
  label, so it has no hard dependency at all.
- **New first-party modules land in typed scope once NG-0.9 exists.** That is a
  rule NG-0.9 imposes on later items, not a prerequisite those items have.
- **NG-1.2 prefers NG-1.1**, because Flink can produce the curated serving
  stream — but NG-1.2 explicitly permits evaluation from an isolated Kafka
  projection first.
- **NG-1.1 recommends NG-0.3**, so lineage impact is visible. Its own acceptance
  evidence — parity, the failure matrix, resource measurement — needs no catalog.
- **NG-2.1 SHALL NOT be started merely because its dependency is met.** Its
  product decision forbids installing MLflow before a real ML/agent slice exists,
  which in practice binds it to NG-2.2.
- **NG-1.3 is conditional on a paper gate** before anything is provisioned: if no
  distinct application-serving query corpus can be defined, its own correct
  outcome is `DO NOT IMPLEMENT`.

### Recommended ordering

Recommended ordering: `docs/adr/0003-next-generation-backlog-prioritisation.md`

That document records the recommended execution order. It is a preference, not an
authorisation and not a dependency. `validate_backlog.py` reads the pointer above
and fails if the ordering it publishes places any item before one of its hard
dependencies — the defect class that produced the NG-0.9 contradiction.

## Dependency layers

Derived from the register above, not maintained separately. `validate_backlog.py`
recomputes this layering from the `Depends on` column and fails if the register
cannot produce it — so a drawing that disagrees with the table is a build error,
not a documentation nit.

An item's layer is the longest dependency path reaching it. **Items in the same
layer have no dependency on each other**, which is where the available
parallelism is.

```text
layer 0   NG-0.1  provenance / identity contract    -
          NG-0.9  engineering quality gates         -

layer 1   NG-0.2  OpenLineage                       needs 0.1
          NG-0.4  OTel Collector                    needs 0.1
          NG-1.2  ClickHouse hot analytics          needs 0.1
          NG-2.1  MLflow governance                 needs 0.1

layer 2   NG-0.3  OpenMetadata                      needs 0.1, 0.2
          NG-0.5  Tempo                             needs 0.4
          NG-0.6  Loki                              needs 0.4
          NG-1.1  Flink shadow path                 needs 0.1, 0.2, 0.4

layer 3   NG-0.7  correlation / SLO                 needs 0.3, 0.4, 0.5, 0.6
          NG-1.3  Pinot serving                     needs 1.1, 1.2

layer 4   NG-0.8  data reliability                  needs 0.3, 0.7

layer 5   NG-2.2  incident agent                    needs 0.3, 0.5, 0.6, 0.7, 0.8, 2.1
```

Layering is a dependency fact, not a schedule. Two items sharing a layer may
still be impossible to verify at the same time: several carry opt-in Compose
profiles whose combined resource demand exceeds a single developer host, and
that ceiling binds harder than the graph does. Sequencing within a layer is a
decision for the operator at authorisation time.

The layering is *permissive*, not prescriptive. NG-1.2 and NG-2.1 sit in layer 1
because nothing technically blocks them there; ADR-0003 still schedules both
late, for reasons the graph cannot express.

## Cross-cutting non-negotiable invariants

1. **Iceberg remains canonical analytical truth.** ClickHouse and Pinot are rebuildable serving projections unless a later, separately authorised architecture decision changes ownership.
2. **The existing PostgreSQL `dwh` database remains business/warehouse state.** OpenMetadata and MLflow SHALL use separate databases/users and SHALL NOT use `dwh` schemas as their control-plane store.
3. **OpenLineage is the lineage protocol boundary.** Product-specific APIs MAY supplement gaps, but runtime lineage SHALL NOT become inseparably coupled to one catalog backend.
4. **Prometheus and Grafana remain.** OpenTelemetry, Tempo, and Loki extend the existing observability stack; the first implementation SHALL NOT replace proven metrics and dashboards.
5. **No floating `latest` tags.** Every new image, connector and Python/Java dependency SHALL be pinned. A compatibility matrix SHALL be recorded in evidence at implementation time.
6. **No product enters the default/core Compose path merely because it works.** Resource-heavy services SHALL live behind opt-in Compose profiles and profile-specific clean-stack CI.
7. **No new claim of "exactly once" is accepted from documentation alone.** The repository SHALL prove the claimed end-to-end semantics under crash/restart/replay with observable state.
8. **Telemetry and metadata control planes SHALL NOT be required for business processing to remain correct.** An outage may reduce observability, but SHALL NOT corrupt or redefine data-plane semantics.
9. **No silent weakening of tests, quality rules, freshness semantics, FF-14, recovery, snapshot provenance, or current M5/H1/S1 gates.**
10. **A product may legitimately end in `DO NOT ADOPT`.** A failed benefit/cost gate is a successful experiment if the evidence is complete.
11. **Benchmarks SHALL use measured denominators.** Synthetic microbenchmarks may bound cost but SHALL NOT be presented as production materiality.
12. **All ML/agent code is software.** It receives the same linting, typing, tests, architecture boundaries, observability, secrets handling, reproducibility, and CI treatment as backend/data code.
13. **DVC, lakeFS, Marquez-as-primary-UI, SigNoz-as-replacement, and a second architecture-linter framework are deferred.** They SHALL NOT be added unless a later spec proves a gap not covered by Iceberg snapshots, OpenMetadata, OpenLineage, Grafana/OTel, and the existing architecture gates.

## Compose/profile policy

The target developer stack SHALL be decomposable rather than requiring every product simultaneously:

```text
core                 existing data platform
metadata             OpenMetadata + OpenSearch dependencies
observability-next   OTel Collector + Tempo + Loki
flink                Flink JobManager/TaskManager + required connectors
clickhouse           ClickHouse
pinot                Pinot cluster components, reusing existing Kafka
ml                   MLflow
```

A profile SHALL declare measured peak RAM/CPU/disk use and a clean-start test. Core H1 SHALL remain runnable without the optional profiles.

## OpenSpec delivery contract

For every numbered spec:

- open one bounded OpenSpec change;
- restate the spec's scope and non-goals in `proposal.md`;
- resolve implementation-specific choices in `design.md`;
- include negative tests where a forbidden state can otherwise silently regress;
- produce evidence before changing a conditional `EXPERIMENT` to `ADOPT`;
- run focused tests, repository gates, profile clean-stack CI, and applicable H1/M5/S1 gates;
- archive the change before starting a dependent state-mutating change;
- stop only for a genuinely unresolved architectural ownership decision, destructive migration, insufficient evidence, or an explicit hard stop in that spec.

## Definition of program success

The program is complete only when an operator can:

1. start from a business/data asset and see upstream/downstream lineage and ownership;
2. start from a failed or slow run and navigate metrics → trace → logs → affected data assets;
3. reproduce which code, source offsets, run/cycle/load identifiers and Iceberg snapshot produced a result;
4. demonstrate a stateful Flink streaming implementation without weakening existing Spark/Iceberg semantics;
5. use ClickHouse for measured hot analytical workloads and Pinot only for a distinct application-serving workload if justified;
6. evaluate any ML/LLM/agent change against immutable, versioned evaluation evidence instead of subjective judgement.
