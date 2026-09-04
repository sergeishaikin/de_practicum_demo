# NG-2.2 — Evaluated Data Platform Incident Agent

> **Lifecycle:** PLANNED
> **Disposition:** pending
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Opens as:** `evaluate-data-platform-incident-agent`
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Freshness of external assumptions

Versions, compatibility matrices, resource requirements, connector capabilities and product limitations recorded in this item are planning assumptions, not frozen truths. They were recorded against the baseline branch named above and are not re-verified while the item sits in the backlog.

- **WHEN** this item is promoted to an authorised change
- **THEN** every externally time-sensitive premise SHALL be re-verified against primary documentation before the design is accepted
- **AND** a premise that cannot be re-verified SHALL be recorded as unverified rather than carried forward on the authority of this document.

## Capability decision

Build one concrete AI vertical slice only after MLflow governance and the metadata/observability foundation exist: a **Data Platform Incident Agent** answering questions such as "Why is `gold.orders_daily_metrics` stale?" using governed platform evidence.

This is the proving ground for agent engineering practices; it is not authorised to mutate production/canonical state.

## Dependencies

**Hard:** NG-2.1, NG-0.3, NG-0.5, NG-0.6, NG-0.7, NG-0.8.

Every one is a tool this agent reads. The catalog supplies lineage; Tempo and
Loki supply the traces and logs whose *absence* one acceptance scenario requires
the agent to distinguish from a data-plane failure; correlation and the
reliability model supply the freshness and severity context another scenario
turns on. NG-0.4 follows transitively through NG-0.5 and NG-0.6.

These were named in this section but only NG-2.1 reached the register, where they
had been arriving transitively through NG-2.1's own over-broad dependency list.
Trimming that list would have silently un-gated this item, so they are now
recorded explicitly. Reconciled on 2026-08-19 in
`reconcile-next-generation-hard-dependencies`.

## Goal

Demonstrate an agent whose quality can be measured against fixed incidents and whose answers cite/derive from real lineage, telemetry, orchestration and Iceberg state rather than hallucinated platform knowledge.

## Initial tool/data scope

Read-only access MAY include:

- OpenMetadata asset/lineage metadata;
- Prometheus/Grafana metrics/query endpoints through a bounded adapter;
- Tempo traces;
- Loki logs;
- Airflow run/task state;
- Iceberg snapshot/catalog metadata;
- repository/runbook documentation.

Write/destructive tools are out of scope.

## Non-goals

- No autonomous remediation.
- No shell/Docker/GitHub mutation from the agent.
- No changes to Kafka offsets, Iceberg tables, Airflow runs or database state.
- No live incident "success" without offline eval.
- No generic chatbot.

## ADDED Requirements

### Requirement: Fixed incident evaluation corpus

Before tuning the agent, create a versioned golden/development corpus with incidents such as:

- Kafka/source lag;
- failed Airflow/dbt freshness gate;
- Iceberg catalog/storage failure;
- FF-14 equal-version conflict;
- medallion cycle failure;
- telemetry/backend outage distinguishable from data-plane outage;
- stale/no-op Gold;
- missing-arrival vs source-freshness distinction.

Each case SHALL include expected root-cause class and required/forbidden conclusions.

### Requirement: Holdout incidents are separate

A holdout incident set SHALL be unavailable to routine prompt tuning. Promotion SHALL evaluate it under NG-2.1 rules.

### Requirement: Evidence citation is required

The agent SHALL return the evidence used for diagnosis (asset/run/metric/trace/log/snapshot identifiers or bounded references). An unsupported root-cause assertion SHALL score as a failure even if the prose sounds plausible.

### Requirement: Uncertainty is valid behavior

If required evidence is unavailable or contradictory, the agent SHALL say the diagnosis is not established and identify missing evidence.

Hallucinating a root cause to always produce an answer is a regression.

### Requirement: Read-only tool boundary

Agent tools SHALL be enforced read-only at the integration layer. Prompt text alone SHALL NOT be the security boundary.

### Requirement: Tool inputs are validated

Dataset names, time ranges, query parameters and IDs passed to tools SHALL be schema-validated and bounded. Arbitrary SQL/shell execution is forbidden in the initial slice.

### Requirement: Prompt and agent versions are governed

System prompts, routing prompts and other accepted prompt artifacts SHALL be MLflow-versioned. Agent code revision and dependency lock SHALL be recorded with each evaluation.

### Requirement: Deterministic scorers cover critical correctness

At minimum code-based scorers SHALL test:

- correct root-cause class;
- no forbidden destructive recommendation where scenario forbids it;
- evidence references present;
- uncertainty used when evidence is insufficient;
- distinction between arrival SLA and freshness;
- FF-14 semantics not rewritten as arrival-order behavior.

LLM judges MAY supplement style/explanation quality but SHALL NOT be the sole correctness gate.

### Requirement: Baseline comparison

Every accepted agent change SHALL compare against an immutable baseline on the same eval dataset/scorers and pass holdout/non-regression thresholds.

### Requirement: Agent observability does not replace platform OTel

Agent execution SHOULD be traced/evaluated in MLflow as appropriate, while platform service telemetry remains in the OTel/Grafana stack. Cross-links MAY be added; one system SHALL NOT masquerade as the other.

### Requirement: No remediation until a later spec

Any proposal for auto-remediation requires a separate security/approval/rollback spec and is outside this change.

## Non-functional requirements

- bounded query/time windows;
- read-only least-privilege credentials;
- prompt-injection-aware tool boundary;
- no secrets/full sensitive logs sent to model providers;
- latency/cost measured;
- reproducible evaluation;
- understandable failure categories.

## Acceptance scenarios

#### Scenario: Gold stale because dbt freshness fails

- **WHEN** the incident fixture contains a fail-closed freshness error
- **THEN** the agent identifies the freshness failure and affected lineage
- **AND** does not falsely claim missing upstream arrival unless evidence supports it.

#### Scenario: Telemetry backend is down but data plane is healthy

- **WHEN** Tempo/Loki data is unavailable but canonical processing succeeds
- **THEN** the agent reports insufficient telemetry / observability impairment
- **AND** does not diagnose a data-processing failure without evidence.

#### Scenario: Evidence conflicts

- **WHEN** metrics and run metadata cannot establish one root cause
- **THEN** the agent states uncertainty and names the next read-only evidence required.

## Acceptance gates

- >= one versioned golden set and separate holdout;
- immutable baseline;
- deterministic critical scorers;
- prompt/version provenance;
- read-only enforcement test including attempted write/destructive prompt;
- prompt-injection/tool-boundary tests;
- offline candidate-vs-baseline report;
- holdout gate;
- latency/cost receipt;
- no canonical state mutation.

## Rollback

Repoint the agent alias to the prior approved version or disable the agent. No data-plane rollback.

## Hard stops

Stop before adding any mutation/remediation tool, sending unredacted sensitive telemetry to an external model, or accepting a quality improvement that lacks comparable eval/holdout evidence.
