## Context

See proposal.md — Why. Three constraints shape the approach.

**The analysis already exists; this change is about where it lives.** The
ranking, the wave order and the parallelism finding were produced against this
branch and reviewed. The work here is placement, normative framing and expiry
conditions — not re-deriving the conclusions.

**A prioritisation is the artifact most likely to be read as permission.** It
names a first item, an order and a preferred branch. Every one of those reads as
a green light unless the document says otherwise in its own voice, at the top,
before the ordering. That placement is a design decision, not formatting.

**It will go stale in a specific, predictable way.** The ranking rests on premises
that implementation evidence can invalidate — OpenMetadata's connector coverage,
Pinot's use case, the AI branch's provider cost, the real resource ceiling. A
prioritisation with no expiry conditions becomes a stale instruction that outlives
its reasoning.

## Goals / Non-Goals

**Goals:**

- One recorded programme-level view of what to do first, with reasoning that can
  be argued against later.
- Normative separation of priority from authorisation, stated before any ordering
  appears.
- The parallelism finding recorded as *policy* rather than advice, because the
  dependency layering actively invites the opposite conclusion.
- Explicit reopen conditions, so a superseded premise produces an amendment
  rather than silent drift.

**Non-Goals:**

- Not evaluating technology choices. OpenMetadata versus DataHub is decided in
  `add-openmetadata-catalog`, on evidence.
- Not scheduling: no dates, owners or capacity.
- Not resolving the register's two recorded contradictions. Those stop the change
  that reaches them.
- Not starting `NG-0.9`.

## Decisions

**An ADR, not a section in `NG-0.9`'s future design.** The content decides four
things that bind items other than `NG-0.9`: the preflight obligation on
`add-openmetadata-catalog`, the slice binding `NG-2.1` to `NG-2.2`, the preferred
branch, and the profile-concurrency policy. A decision that constrains thirteen
other items cannot live inside the design of one of them — the twelve items whose
authors never read `NG-0.9`'s design would not find it.

**The normative statement goes first, above the context.** ADR-0002 opens with
context, which is the usual shape. This one inverts it. A reader skimming for
"what do I do first" hits the ordering; the point that ordering is not permission
has to be upstream of that, or it is structurally unreachable by the reader most
likely to misuse the document.

**"Recommended path to the first differentiated end-state", not "critical
path".** The earlier analysis called the chain
`0.9 → 0.1 → 0.2 → 0.3 → 0.7 → 0.8 → 2.1 → 2.2` the critical path. That term
asserts a single mathematical longest path to a fixed terminus, and this
programme has no fixed terminus: `NG-1.3` may end in `DO NOT IMPLEMENT`, the
`1.x`/`2.x` fork is genuine, and any `EXPERIMENT` item may end in `REMOVE` —
which the register's invariant 10 calls a successful outcome. Precision here is
not pedantry: "critical path" implies the work is mandatory, and four of the
fourteen items explicitly are not.

**OM-PREFLIGHT is a gate inside `add-openmetadata-catalog`, not a new NG item.**
`NG-0.3` is the programme's largest rework risk — XL, resource-heavy, and with
the most expensive fallback of any item. A bounded compatibility gate before the
expensive integration is the standard mitigation. Making it a fifteenth backlog
item would grow the register an entry for every risk-reduction step and require a
separate authorisation to de-risk work already authorised.

**`NG-2.1` + `NG-2.2` are scheduled as one slice but stay two changes.** The
governance boundary — one bounded change, one authorisation — is unchanged.
What is recorded is that scheduling them into distant waves would violate
`NG-2.1`'s own product decision, which forbids installing MLflow before a real
ML/agent use case exists.

**Parallelism is written as policy, with the two ceilings named separately.**
Authoring concurrency is bounded by file ownership; live-profile concurrency is
bounded by memory. The layering makes the second mistake attractive, because
independent subtrees look like independent capacity. The explicit prohibition on
a combined `core + metadata + flink + pinot + ml` acceptance test exists because
that is the concrete form the mistake takes.

**No spec delta, declared rather than omitted.** Every rule the ADR obeys was
ratified by `add-next-generation-backlog`. Restating "priority is not
authorisation" as a new requirement would create two statements of one rule that
can drift apart — the same defect this programme's register was restructured to
remove. Three archived changes set the precedent that a change need not carry a
delta.

`openspec validate --strict` rejects a change with no deltas by default, which is
the right default: a change that quietly modifies no capability is usually a
change that forgot to say what it changed. The tool's own mechanism for the
legitimate case is `skip_specs: true` in `.openspec.yaml`, which this change
sets. The distinction matters — the absence of a delta here is a declared
property of the change, not an oversight that happened to pass.

## Risks / Trade-offs

**A recommendation recorded as an ADR carries more weight than a recommendation
should.** ADR-0001 and ADR-0002 decide platform behaviour; this one decides a
preference. Mitigated by the status line and the opening statement, both of which
say so explicitly, and by the reopen conditions — but the asymmetry is real, and
a reader who trusts the format over the content will over-read it.

**Estimates are relative and unmeasured.** No profile receipt exists for any NG
capability, because none has been built; `NG-0.1` is the item that would require
them. Every S/M/L/XL and every resource claim is therefore a judgement, and the
ADR says so in the parallelism section rather than in a footnote.

**Recommending a branch may foreclose the other in practice.** Preferring the AI
branch over Flink is a recommendation, but recommendations attract effort. The
mitigation is weak by design: `NG-1.1` keeps its full specification and its
`EXPERIMENT` gate, and the comparison table states the streaming branch's value
in its own terms rather than as a runner-up.
