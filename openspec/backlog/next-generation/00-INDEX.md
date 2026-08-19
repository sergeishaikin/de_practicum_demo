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
single source of truth for order, dependencies, change ids and authorisation
state; `validate_backlog.py` in the parent directory parses it and fails if any
of those invariants break.

Every item below is a **recorded backlog item**, not authorised work. Each opens
as its own OpenSpec change under `openspec/changes/` when — and only when — the
operator authorises it. Row order is the execution order and SHALL remain
topologically valid: an item's dependencies always appear in earlier rows.

Column contracts, so the register stays parseable:

- **Item** — `NG-<major>.<minor>`, unique.
- **Gate** — exactly `ADOPT` or `EXPERIMENT`. Conditional wording belongs in the
  item, not here.
- **Depends on** — comma-separated item ids, or `-` for none. **Hard**
  dependencies only; soft preferences are recorded in the notes below.
- **Opens as** — the pre-assigned OpenSpec change id, unique.
- **Authorised** — `no`, or the ISO date the operator authorised it.

| Item | File | Gate | Depends on | Opens as | Authorised |
|---|---|---|---|---|---|
| NG-0.1 | `NG-0.1-platform-provenance-contract.md` | ADOPT | - | `add-platform-provenance-contract` | no |
| NG-0.2 | `NG-0.2-openlineage.md` | ADOPT | NG-0.1 | `add-openlineage-runtime-lineage` | no |
| NG-0.3 | `NG-0.3-openmetadata.md` | ADOPT | NG-0.1, NG-0.2 | `add-openmetadata-catalog` | no |
| NG-0.4 | `NG-0.4-opentelemetry-collector.md` | ADOPT | NG-0.1 | `add-opentelemetry-collector` | no |
| NG-0.5 | `NG-0.5-grafana-tempo.md` | ADOPT | NG-0.4 | `add-tempo-trace-backend` | no |
| NG-0.6 | `NG-0.6-grafana-loki.md` | ADOPT | NG-0.4 | `add-loki-log-backend` | no |
| NG-0.7 | `NG-0.7-grafana-correlation.md` | ADOPT | NG-0.3, NG-0.4, NG-0.5, NG-0.6 | `add-grafana-correlation-slo` | no |
| NG-0.8 | `NG-0.8-data-reliability.md` | ADOPT | NG-0.3, NG-0.7 | `unify-data-reliability` | no |
| NG-0.9 | `NG-0.9-engineering-quality-gates.md` | ADOPT | NG-0.1 | `add-static-typing-gate` | no |
| NG-1.1 | `NG-1.1-apache-flink-shadow-streaming.md` | EXPERIMENT | NG-0.1, NG-0.2, NG-0.3, NG-0.4, NG-0.5, NG-0.6, NG-0.7, NG-0.9 | `evaluate-flink-shadow-streaming` | no |
| NG-1.2 | `NG-1.2-clickhouse-hot-analytics.md` | EXPERIMENT | NG-0.1, NG-0.4, NG-0.5, NG-0.6, NG-0.7, NG-0.8, NG-0.9 | `evaluate-clickhouse-hot-analytics` | no |
| NG-1.3 | `NG-1.3-apache-pinot-realtime-serving.md` | EXPERIMENT | NG-1.1, NG-1.2 | `evaluate-pinot-realtime-serving` | no |
| NG-2.1 | `NG-2.1-mlflow-ai-governance.md` | ADOPT | NG-0.1, NG-0.3, NG-0.4, NG-0.5, NG-0.6, NG-0.7, NG-0.8, NG-0.9 | `add-mlflow-ai-governance` | no |
| NG-2.2 | `NG-2.2-data-platform-incident-agent.md` | EXPERIMENT | NG-2.1 | `evaluate-data-platform-incident-agent` | no |

A row changes only in two ways: `Authorised` flips to the date the operator
authorised it, and the row records the change's disposition once the change is
archived. A backlog row SHALL NOT be edited to look like progress that the change
record does not carry.

### Soft preferences and one unresolved tension

The `Depends on` column records only what SHALL be complete first. These are
recorded here rather than in the column because they are not gating:

- **NG-1.2** prefers NG-1.1, because Flink can produce the curated serving
  stream — but NG-1.2 explicitly permits evaluation from an isolated Kafka
  projection first, so it is not gated on Flink.
- **NG-2.1** SHALL NOT be started merely because its dependencies are met. Its
  own product decision forbids installing MLflow before a real ML/agent slice
  exists, which in practice binds it to NG-2.2.

### Recorded contradictions

Two places where the package disagrees with itself. Both are recorded rather
than silently decided, and neither may be settled by an implementing change's
design alone — see *Backlog contradictions stop implementation* in
`openspec/specs/engineering-governance/spec.md`.

- **NG-1.1 — required or recommended?** Its `Dependencies` section lists "NG-0.1
  through NG-0.7", which includes NG-0.3, and then states that OpenMetadata is
  "recommended before adoption". Both cannot be true. The register carries the
  **stricter reading** as a provisional interpretation — NG-0.3 is a hard
  dependency — because over-gating can only delay work whereas under-gating can
  start it prematurely. This is an interim reading, not a resolution.
- **NG-1.2 — weaker in the item than in the register.** The item states "NG-0.1
  and observability/quality gates"; the register carries NG-0.1 and
  NG-0.4 – NG-0.9. The register is again the stricter reading.

When `evaluate-flink-shadow-streaming` or `evaluate-clickhouse-hot-analytics` is
authorised, it SHALL stop before state-changing work and have the contradiction
resolved — as a bounded backlog correction, or as an authoritative
interpretation recorded in this register — **before** its own design is
accepted. An implementing change SHALL NOT decide retroactively which line of
the backlog was the correct one.

## Dependency layers

Derived from the register above, not maintained separately. `validate_backlog.py`
recomputes this layering from the `Depends on` column and fails if the register
cannot produce it — so a drawing that disagrees with the table is a build error,
not a documentation nit.

An item's layer is the longest dependency path reaching it. **Items in the same
layer have no dependency on each other**, which is where the available
parallelism is.

```text
layer 0   NG-0.1  provenance / identity contract

layer 1   NG-0.2  OpenLineage                     needs 0.1
          NG-0.4  OTel Collector                  needs 0.1
          NG-0.9  engineering quality gates       needs 0.1

layer 2   NG-0.3  OpenMetadata                    needs 0.2
          NG-0.5  Tempo                           needs 0.4
          NG-0.6  Loki                            needs 0.4

layer 3   NG-0.7  correlation / SLO               needs 0.3, 0.4, 0.5, 0.6

layer 4   NG-0.8  data reliability                needs 0.3, 0.7
          NG-1.1  Flink shadow path               needs 0.1-0.7, 0.9

layer 5   NG-1.2  ClickHouse hot analytics        needs 0.1, 0.4-0.9
          NG-2.1  MLflow governance               needs 0.1, 0.3-0.9

layer 6   NG-1.3  Pinot serving                   needs 1.1, 1.2
          NG-2.2  incident agent                  needs 2.1
```

Layering is a dependency fact, not a schedule. Two items sharing a layer may
still be impossible to verify at the same time: several carry opt-in Compose
profiles whose combined resource demand exceeds a single developer host, and
that ceiling binds harder than the graph does. Sequencing within a layer is a
decision for the operator at authorisation time.

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
