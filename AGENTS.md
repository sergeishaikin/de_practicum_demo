# Architecture Audit Kit — Minimal Sufficient Architecture

## Core engineering principle

Prefer the smallest design and implementation that fully satisfies demonstrated requirements and required quality attributes.

Before adding code, dependencies, abstractions, configuration, state, or infrastructure, check whether the goal can instead be met by:

1. doing nothing;
2. deleting or consolidating existing code;
3. reusing an existing implementation;
4. using the standard library;
5. using a native platform/framework capability;
6. using an already-installed dependency.

Add a new abstraction only when a concrete present requirement, demonstrated isolation need, or multiple real use cases justify it.

Do not design extension points for hypothetical future requirements.

When multiple approaches are correct, prefer the one with fewer:
- concepts;
- components;
- dependencies;
- state transitions;
- configuration options;
- operational responsibilities.

Minimal does not mean fragile. Never remove required validation, security, transactional guarantees, idempotency, deterministic behavior, concurrency safety, recovery semantics, schema compatibility, observability, performance safeguards, or tests merely to reduce code.

For non-trivial changes:
- inspect the actual code path first;
- distinguish evidence from inference and assumptions;
- preserve existing contracts unless change is required;
- state what is explicitly out of scope;
- establish a complexity budget before implementation;
- run an adversarial simplicity challenge before acceptance.

Treat SOLID, DRY, design patterns, DDD, Clean Architecture, layering, and architectural boundaries as tools, not goals. Introduce them only when they reduce total system complexity or satisfy a demonstrated requirement.

A solution is not complete merely because it works.

Correct but unnecessarily complicated != DONE.
Simple but operationally unsafe != DONE.
Architecturally elegant but unsupported by requirements != DONE.
