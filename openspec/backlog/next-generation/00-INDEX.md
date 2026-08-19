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

## Backlog status and authorisation

Every item below is a **recorded backlog item**, not authorised work. Each opens
as its own OpenSpec change under `openspec/changes/` when — and only when — the
operator authorises it. The `Opens as` column fixes the change id in advance so
that the same work cannot be started twice under two names.

| Item | Capability | Decision gate | Depends on | Opens as | Authorised |
|---|---|---|---|---|---|
| NG-0.1 | Platform identity, provenance, product guardrails | ADOPT | current baseline | `add-platform-provenance-contract` | no |
| NG-0.2 | OpenLineage runtime lineage protocol | ADOPT if end-to-end edge coverage is proven | NG-0.1 | `add-openlineage-runtime-lineage` | no |
| NG-0.3 | OpenMetadata catalog, lineage and data UI | ADOPT unless a documented blocker forces fallback evaluation | NG-0.1, NG-0.2 | `add-openmetadata-catalog` | no |
| NG-0.4 | OpenTelemetry Collector + instrumentation contract | ADOPT | NG-0.1 | `add-opentelemetry-collector` | no |
| NG-0.5 | Grafana Tempo trace backend | ADOPT | NG-0.4 | `add-tempo-trace-backend` | no |
| NG-0.6 | Grafana Loki log backend | ADOPT | NG-0.4 | `add-loki-log-backend` | no |
| NG-0.7 | Grafana correlation, SLI/SLO and cross-links | ADOPT | NG-0.3–NG-0.6 | `add-grafana-correlation-slo` | no |
| NG-0.8 | Unified data quality, freshness, SLA/SLO context | ADOPT | NG-0.3, NG-0.7 | `unify-data-reliability` | no |
| NG-0.9 | Static typing + uniform software/architecture quality | ADOPT | NG-0.1 | `add-static-typing-gate` | no |
| NG-1.1 | Apache Flink shadow streaming path | EXPERIMENT → ADOPT / KEEP / REMOVE | NG-0.1–NG-0.7, NG-0.9 | `evaluate-flink-shadow-streaming` | no |
| NG-1.2 | ClickHouse hot operational analytics | EXPERIMENT → ADOPT / REMOVE | NG-0.1, NG-0.4–NG-0.9; preferably NG-1.1 | `evaluate-clickhouse-hot-analytics` | no |
| NG-1.3 | Apache Pinot application-facing real-time serving | EXPERIMENT → ADOPT / REMOVE | NG-1.1; distinct use case from NG-1.2 | `evaluate-pinot-realtime-serving` | no |
| NG-2.1 | MLflow experiments, prompt/model registry, evals | ADOPT only with a real ML/agent slice | NG-0.1, NG-0.3–NG-0.9 | `add-mlflow-ai-governance` | no |
| NG-2.2 | Evaluated Data Platform Incident Agent | EXPERIMENT → ADOPT / REMOVE | NG-2.1 and operational metadata/telemetry | `evaluate-data-platform-incident-agent` | no |

A row changes only in two ways: `Authorised` flips to the date the operator
authorised it, and the row records the change's disposition once the change is
archived. A backlog row SHALL NOT be edited to look like progress that the
change record does not carry.

## Execution order

| Order | File | Product / capability | Decision gate | Depends on |
|---|---|---|---|---|
| 0.1 | `NG-0.1-platform-provenance-contract.md` | Platform identity, provenance, product guardrails | ADOPT | current baseline |
| 0.2 | `NG-0.2-openlineage.md` | OpenLineage runtime lineage protocol | ADOPT if end-to-end edge coverage is proven | 0.1 |
| 0.3 | `NG-0.3-openmetadata.md` | OpenMetadata catalog, lineage and data UI | ADOPT unless a documented blocker forces fallback evaluation | 0.1, 0.2 |
| 0.4 | `NG-0.4-opentelemetry-collector.md` | OpenTelemetry Collector + instrumentation contract | ADOPT | 0.1 |
| 0.5 | `NG-0.5-grafana-tempo.md` | Grafana Tempo trace backend | ADOPT | 0.4 |
| 0.6 | `NG-0.6-grafana-loki.md` | Grafana Loki log backend | ADOPT | 0.4 |
| 0.7 | `NG-0.7-grafana-correlation.md` | Grafana correlation, SLI/SLO and cross-links | ADOPT | 0.3–0.6 |
| 0.8 | `NG-0.8-data-reliability.md` | Unified data quality, freshness, SLA/SLO context | ADOPT | 0.3, 0.7 |
| 0.9 | `NG-0.9-engineering-quality-gates.md` | Static typing + uniform software/architecture quality | ADOPT | 0.1 |
| 1.1 | `NG-1.1-apache-flink-shadow-streaming.md` | Apache Flink shadow streaming path | EXPERIMENT → ADOPT / KEEP / REMOVE | 0.1–0.7, 0.9 |
| 1.2 | `NG-1.2-clickhouse-hot-analytics.md` | ClickHouse hot operational analytics | EXPERIMENT → ADOPT / REMOVE | 0.1, 0.4–0.9; preferably 1.1 |
| 1.3 | `NG-1.3-apache-pinot-realtime-serving.md` | Apache Pinot application-facing real-time serving | EXPERIMENT → ADOPT / REMOVE | 1.1; distinct use case from 1.2 |
| 2.1 | `NG-2.1-mlflow-ai-governance.md` | MLflow experiments, prompt/model registry, evals | ADOPT only with a real ML/agent slice | 0.1, 0.3–0.9 |
| 2.2 | `NG-2.2-data-platform-incident-agent.md` | Evaluated Data Platform Incident Agent | EXPERIMENT → ADOPT / REMOVE | 2.1 and operational metadata/telemetry |

## Dependency graph

```text
0.1 provenance / invariants
 |
 +--> 0.2 OpenLineage --> 0.3 OpenMetadata ---+
 |                                            |
 +--> 0.4 OTel Collector --> 0.5 Tempo -------+
 |                       \-> 0.6 Loki --------+
 |                                            |
 +--> 0.9 engineering gates                   |
                                              v
                                    0.7 correlation / SLO
                                              |
                                              v
                                      0.8 reliability
                                              |
                                              v
                                 1.1 Flink shadow path
                                    |            |
                                    v            v
                             1.2 ClickHouse   1.3 Pinot

0.3 + 0.7 + 0.8 + 0.9 --> 2.1 MLflow --> 2.2 Incident Agent
```

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
