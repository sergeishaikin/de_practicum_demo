# NG-0.9 — Uniform Engineering Quality and Static Analysis Gates

> **Status:** PROPOSED — future-state specification
> **Execution authorization:** NONE. This file specifies a future bounded change; it does not authorize implementation by itself.
> **Repository:** `sergeishaikin/de_practicum_demo`
> **Baseline branch used for analysis:** `test/dbt-extensive-testing`
> **SDD convention:** implementation SHALL be opened as its own OpenSpec change with `proposal.md`, `design.md`, `tasks.md`, evidence, and the required spec delta before code is applied.

Normative terms `SHALL`, `SHALL NOT`, `SHOULD`, and `MAY` are intentional. A requirement is not complete because a container starts; it is complete only when its acceptance evidence is captured and the relevant live CI gates are green.

## Freshness of external assumptions

Versions, compatibility matrices, resource requirements, connector capabilities and product limitations recorded in this item are planning assumptions, not frozen truths. They were recorded against the baseline branch named above and are not re-verified while the item sits in the backlog.

- **WHEN** this item is promoted to an authorised change
- **THEN** every externally time-sensitive premise SHALL be re-verified against primary documentation before the design is accepted
- **AND** a premise that cannot be re-verified SHALL be recorded as unverified rather than carried forward on the authority of this document.

## Decision

Extend the existing quality system instead of installing a second architecture-lint framework. Add a real Python static type checker through a bounded compatibility spike; **Ruff remains the linter and is not treated as a type checker**.

The default candidate is **mypy** because it is mature and CI-friendly, but the implementation change SHALL verify third-party typing compatibility before pinning it. If mypy proves materially unsuitable, the design may select Pyright with recorded evidence; two type checkers SHALL NOT be retained without a proven distinct purpose.

## Dependencies

**None.** This item has no hard technical prerequisite: nothing in it consumes
an identity, dataset name, provenance envelope or telemetry label.

NG-0.1 was previously listed here as an inherited layering convention. It was
removed on 2026-08-19 in `reconcile-next-generation-hard-dependencies`, because
it contradicted ADR-0003's recommendation to run this item first and blocked a
change that nothing technically blocks.

This item SHOULD still be done early — its cost rises with every later item that
adds Python — but that is scheduling, not gating.

## Goal

Apply the same software-engineering standard to future platform, Flink-adjacent Python, metadata adapters, observability code and ML/agent code.

## Non-goals

- No rewrite of working code merely to reach "strict everywhere" in one change.
- No second architecture framework parallel to the existing M5/fitness tests.
- No lint exceptions for ML/agent code as a category.
- No blanket `# type: ignore` migration.

## ADDED Requirements

### Requirement: Ruff and a type checker are complementary

The repository SHALL continue Ruff and SHALL add a type-checking gate for selected first-party Python modules. Lint success SHALL NOT be treated as type-check success.

### Requirement: Typed scope expands monotonically

The initial type-check scope SHALL be explicitly listed. New first-party modules introduced by NG specs SHALL be in typed scope by default.

Legacy modules MAY be onboarded incrementally, but a module already in typed scope SHALL NOT be removed merely to make CI green.

### Requirement: Suppressions are specific

`type: ignore` / checker-specific suppressions SHALL include the narrow error code/reason where supported. Broad file/package exclusions require evidence and an issue/follow-up owner.

### Requirement: Third-party typing gaps do not justify runtime changes

Missing/inaccurate type stubs SHALL be addressed with stubs/protocols/narrow adapters where practical. Production behavior SHALL NOT be changed solely to satisfy an incorrect type model.

### Requirement: Architecture fitness remains executable

Existing M5/architecture tests SHALL remain the primary architecture-lint mechanism. New cross-cutting rules introduced by these NG specs SHOULD become executable tests when deterministic.

Examples include:

- optional profile isolation;
- forbidden canonical writes from serving products;
- exact dependency direction;
- no `latest` images;
- no OpenMetadata/MLflow tables in `dwh`;
- no high-cardinality telemetry label patterns.

### Requirement: ML/agent code follows the same gates

Agent prompts/eval scripts are additional artifacts, not exemptions. Python runtime code for ML/agents SHALL pass formatter, linter, type checker, unit/integration tests and architecture gates applicable to its layer.

### Requirement: CI ordering gives fast feedback

Fast static gates SHOULD run before expensive stack integration tests. A type/lint failure SHALL not require starting the full Docker stack to diagnose.

### Requirement: Coverage is not weakened

The existing enforced coverage threshold SHALL NOT be lowered to land NG work. New logic SHALL carry focused tests; generated/vendor/config-only files may be treated according to existing policy.

## Non-functional requirements

- fast local command documented;
- deterministic versions via `uv.lock`;
- no network-required static analysis during normal CI after dependencies are installed;
- clear failure output;
- Windows/local developer compatibility where repository workflow requires it.

## Acceptance gates

- type checker pinned and in `uv.lock`;
- initial first-party typed scope documented;
- one negative fixture proving the checker catches a type error Ruff does not;
- no broad blanket ignores;
- existing Ruff/Black/SQLFluff/pytest/coverage/M5/H1/S1 gates green;
- architecture fitness tests for at least the new cross-cutting invariants introduced by NG-0.1 where practical.

## External constraint

Ruff's own documentation states that Ruff is a linter, not a type checker, and recommends using it with a type checker such as mypy/Pyright/Pyre. This spec therefore fills a real gap rather than duplicating Ruff.

## Rollback

If the selected checker is incompatible with required libraries, revert only the type-checker change and preserve any independently useful annotations/tests. Changing checker is a new bounded design decision, not an excuse to disable typing permanently.

## Hard stops

Stop if enforcing the selected checker requires large unrelated runtime refactors or forces incompatible dependency downgrades. Produce a compatibility report and choose the checker in design.
