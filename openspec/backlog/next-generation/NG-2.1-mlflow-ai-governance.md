# NG-2.1 — MLflow Evaluation, Experiment and Prompt/Model Governance

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Product decision

Adopt **MLflow** only when a real ML/LLM/agent vertical slice is ready. MLflow will provide experiment tracking, evaluation datasets, prompt/model versioning/registry, artifacts and reproducibility evidence.

The program SHALL NOT install MLflow first and invent a use case later.

## Dependencies

NG-0.1, NG-0.3 through NG-0.9.

## Goal

Make every ML/LLM/agent change answerable with evidence: what data, code, prompt/model, scorer versions and configuration were used, what baseline it beat or regressed, and whether holdout performance stayed acceptable.

## Non-goals

- No subjective "looks better" acceptance.
- No same dataset used as both tuning set and final holdout.
- No prompt kept only as an unversioned Python string for accepted experiments.
- No DVC/lakeFS for Iceberg-resident structured datasets without a proven gap.
- No mixing classic ML and GenAI evaluation APIs/metric objects as if interoperable.
- No ML code exemption from NG-0.9.

## ADDED Requirements

### Requirement: Isolated MLflow persistence

MLflow SHALL use a dedicated PostgreSQL database/user and a dedicated artifact bucket/prefix. It SHALL NOT store tracking tables in `dwh`.

The local platform MAY reuse the existing PostgreSQL server and S3-compatible object store with strict logical/credential separation.

### Requirement: Fixed evaluation dataset exists before optimization

A curated, versioned evaluation dataset SHALL exist before a prompt/model/agent optimization is accepted. It SHALL contain representative normal, edge and known-failure cases.

### Requirement: Golden/development set and holdout are distinct

The evaluation program SHALL distinguish:

- a development/golden regression set used during iteration;
- a holdout set not used to tune prompts/models/scorers.

Holdout membership SHALL not be silently copied into the development set to improve a score.

### Requirement: Baseline is immutable evidence

Before claiming improvement, an immutable baseline run SHALL record the same evaluation dataset version/digest, scorer versions, relevant model/provider configuration and code revision.

If a comparable baseline does not exist, the result is `NOT ESTABLISHED`; a substitute denominator SHALL NOT be invented.

### Requirement: Prompt versions are registered

Accepted LLM/agent prompts SHALL be registered as immutable versions with provenance. Changing a prompt creates a new version; overwriting the old text in place is forbidden.

### Requirement: Model versions are registered when models exist

Trainable/model artifacts accepted by the project SHALL use MLflow model versioning/registry or a documented equivalent within MLflow. The originating experiment/run SHALL remain traceable.

### Requirement: Iceberg snapshot is logged for dataset provenance

When training/evaluation data comes from Iceberg, the exact table and snapshot ID SHALL be logged. "latest" alone is insufficient.

For non-Iceberg input, a content digest/version reference SHALL be recorded.

### Requirement: Experiment run captures reproducibility fields

At minimum where applicable:

- git commit SHA;
- code/config version;
- dataset ID/digest and Iceberg snapshot;
- prompt version;
- model/provider + model identifier;
- relevant inference/training parameters;
- scorer set + scorer versions;
- seed where deterministic execution supports it;
- environment/dependency lock reference;
- output metrics/artifacts.

### Requirement: Offline eval is a CI/release gate

A bounded offline evaluation SHALL run for changes that can affect accepted agent/model quality. The gate SHALL compare against an approved baseline and explicit thresholds/tolerances.

Thresholds SHALL be justified and version-controlled.

### Requirement: Scorer validity is tested

Code-based scorers SHALL have unit tests. LLM judges SHALL have a documented model/version/config and SHALL not be treated as deterministic ground truth.

Critical business-correctness rules SHOULD use deterministic code-based scorers where possible.

### Requirement: Classic ML and GenAI eval systems remain separate

If both classic ML and GenAI are present, their MLflow evaluation APIs/metric types SHALL not be mixed. Shared business acceptance criteria MAY be summarized at a higher layer only after each system produces valid results.

### Requirement: Evaluation results are auditable

Per-case results and aggregate metrics needed to explain a gate decision SHALL be retained as MLflow artifacts/metadata for the defined retention period.

### Requirement: Cost/latency are quality dimensions where relevant

For hosted/LLM inference, evaluation SHALL record latency and, where measurable, request/token/cost dimensions. Quality improvement that causes unacceptable operational regression SHALL not be automatically accepted.

## Non-functional requirements

- **Reproducibility:** exact input and prompt/model versions.
- **Security:** provider keys only through secrets; no keys in MLflow params/artifacts.
- **Privacy:** eval sets reviewed for PII/secrets before persistence.
- **Determinism:** deterministic metrics separated from judge-based stochastic metrics.
- **Resource isolation:** `ml` opt-in profile.
- **Maintainability:** experiment conventions and naming documented.

## Acceptance scenarios

#### Scenario: New prompt scores higher on development set

- **WHEN** prompt v2 improves the development/golden score
- **THEN** holdout evaluation still runs
- **AND** adoption requires the configured holdout/non-regression gates.

#### Scenario: No comparable baseline

- **WHEN** dataset/scorer/model conditions differ such that baseline comparison is invalid
- **THEN** the result is recorded as not comparable/not established
- **AND** no percentage improvement is reported.

#### Scenario: Eval dataset uses Iceberg

- **WHEN** a run evaluates against an Iceberg-derived dataset
- **THEN** MLflow records the snapshot ID
- **AND** the run can be reproduced against that snapshot subject to retention.

## Acceptance gates

- MLflow tracking server on isolated DB/artifact store;
- evaluation dataset + holdout management;
- baseline-vs-candidate demo;
- prompt immutable version/diff proof;
- snapshot provenance proof;
- scorer unit tests;
- CI evaluation gate;
- negative test for missing baseline/comparison mismatch;
- secrets scan;
- core platform remains functional with MLflow disabled.

## Verified external constraints

Current MLflow documentation requires a SQL backend for Evaluation Datasets, supports PostgreSQL metadata and S3-compatible artifact stores, provides immutable prompt versions, and explicitly separates classic ML evaluation metrics from GenAI `Scorer` objects.

## Rollback

Disable MLflow/agent profile. Existing data platform remains unaffected. Historical experiment artifacts MAY be retained read-only according to retention policy.

## Hard stops

Stop if an evaluation requires uploading sensitive canonical data to an external provider without explicit approval, if holdout separation cannot be preserved, or if a quality claim has no comparable baseline.
