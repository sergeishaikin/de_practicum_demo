## Context

See proposal.md. The operator authorised a multi-change programme; the standing
spec forbids exactly that. One of them has to change, and it is the spec — but
the change has to preserve why the original rule existed.

## Decisions

**Modify the two requirements rather than add an overriding one.** An added
requirement that contradicts an existing one leaves a spec that says both things,
and a later reader has no way to tell which governs. The carve-out belongs inside
the rules it qualifies.

**The exception is named and singular.** "Unless a recorded bounded programme
authorisation covers it" — not "unless otherwise agreed". The original rule's
value is that it cannot be satisfied by inference, and an exception phrased
loosely would return the whole problem.

**A programme must state its membership as an evaluable rule.** The authorised
programme's rule is `Gate == ADOPT`, taken in ADR-0003 order constrained by the
DAG — all three readable from canonical sources. "Whatever comes next" is
explicitly rejected, because an agent applying it would be choosing its own
scope, which is what per-change authorisation prevents.

**Re-reading canonical sources before each item is a requirement, not advice.**
This programme's own history is the argument: `reconcile-next-generation-hard-dependencies`
moved four items between layers. A plan made at programme start would already be
wrong.

**A programme cannot amend the rules that bound it.** Without this, an agent
blocked by governance has an obvious and catastrophic move available: edit the
governance. It is stated as its own requirement rather than a clause, because it
is the failure mode with the worst consequences and the least visibility.

## Risks / Trade-offs

**The exception is real and it is load-bearing.** The per-change rule was a
strong, simple guarantee, and it is now conditional. The mitigation is that the
condition is a recorded artifact rather than a judgement — but a rule with an
exception is weaker than one without, and that cost is accepted deliberately.

**Recording an authorisation does not make it wise.** This change makes the
programme legible and bounded; it does not evaluate whether the programme is a
good idea. That was the operator's decision.
