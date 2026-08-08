# Anti-Overengineering Orchestration

Use the lightest workflow that matches the risk and architectural impact.

## Small/local change

```text
minimal-design
    ↓
implementation
    ↓
tests
    ↓
simplicity-challenge
```

Use when behavior is local, contracts are obvious, and no durable state/infrastructure/architecture changes are expected.

## Medium change

```text
evidence-analysis
    ↓
minimal-design
    ↓
complexity-budget
    ↓
implementation
    ↓
tests / correctness review
    ↓
simplicity-challenge
    ↓
architecture-balance
    ↓
architecture-acceptance
```

## Architectural / stateful / operationally risky change

```text
evidence-analysis
        ↓
requirements + demonstrated constraints
        ↓
solution design
        ↓
minimal-design
        ↓
complexity-budget
        ↓
implementation plan
        ↓
implementation
        ↓
correctness review + tests
        ↓
reliability / operational review
        ↓
simplicity-challenge
        ↓
architecture-balance
        ↓
architecture-acceptance
```

## Ordering rationale

First prove the solution satisfies the requirements.

Then prove its complexity is necessary.

Do not run simplification as a substitute for correctness review.

## Independent challenger

Where the agent runtime supports subagents or isolated contexts, run `simplicity-challenge` in a separate context from the builder.

The challenger should receive:

- requested requirements;
- evidence/current-state summary;
- proposed or implemented diff;
- relevant tests;
- explicit quality constraints.

Do not provide the builder's persuasive design rationale unless needed as evidence. The challenger should independently test whether each moving part deserves to exist.

## Complexity escalation

If `complexity-budget` returns `COMPLEXITY_BUDGET_EXCEEDED`, do not continue automatically.

Re-run:

```text
evidence-analysis
    ↓
minimal-design
```

using newly discovered facts.

Then either:
- establish a revised justified budget; or
- simplify the design.

## Final invariant

The target is not maximum abstraction, minimum LOC, or perfect conformity to design principles.

The target is:

**minimum architecture sufficient for demonstrated requirements and required quality attributes.**
