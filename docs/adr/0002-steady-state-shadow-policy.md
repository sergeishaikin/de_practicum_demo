# ADR-0002 — Steady-state shadow policy

| | |
|---|---|
| **Status** | **Accepted** — shadow validation is mandatory for as long as persisted Silver is the Gold source; the conditions for reopening the question are stated below and are not currently met |
| **Date** | 2026-08-19 |
| **Deciders** | *(unassigned)* |
| **Supersedes** | nothing. It ratifies, with conditions, a policy that was previously held only as an informal note in `.planning/STATE.md` |
| **Evidence base** | [`artifacts/b2-rollout/06-o1-window.json`](../../artifacts/b2-rollout/06-o1-window.json) — committed, frozen; the receipt-gated fast path as landed by 04-06; `iceberg/common/cutover.py` |

Related: [ADR-0001](0001-incremental-silver-and-gold.md) decides the Silver and Gold execution
model that this policy sits on top of. This ADR does not amend it.

---

## Context

### The question

After a successful, evidenced cutover to `GOLD_SOURCE=persisted_silver`, must `SHADOW_COMPARE`
remain `1` — indefinitely?

It has been answered informally as "yes, keep it on" since M5, and `.planning/STATE.md` records
that answer as a decision: *"Persisted-Silver Gold cutover must keep shadow comparison enabled."*
What it does not record is what evidence would change it. An unstated condition cannot be met,
argued against, or shown to have been met, so the policy has been unfalsifiable rather than
ratified. That is the gap this record closes.

### Why it was ever a question

With `SHADOW_COMPARE=1`, a medallion cycle under `SILVER_MODE=b2` pins a Bronze boundary, builds
the **legacy logical Silver projection in full** from that boundary, and compares it against the
persisted B2 Silver, key by key, over the whitelisted business columns — before Gold is written.
That is a full scan and a full rebuild on every cycle, whether or not anything changed.

The measured cost comes from a single frozen window. Its limits belong next to its figures, not in
a footnote:

> `06-o1-window.json` records **five outer cycles at demo volume** over roughly six minutes on
> 2026-08-10, emitted as ten metric rows. Five rows carry `shadow_comparisons=1`, with
> `silver_duration_ms` between **21,406 and 45,448** and `gold_duration_ms` between **4,130 and
> 5,572**. Exactly one row in the entire window has non-zero `files_processed` and
> `snapshot_delta` — one file, one key, 4,422 bytes planned. **This is a five-cycle sample at one
> volume on one dataset. It establishes no scaling relationship whatsoever.** It establishes only
> that, at that volume, tens of seconds per cycle were being spent while nothing changed.

That is a real objection to permanent validation, and it is the objection this ADR has to answer
rather than dismiss.

### What changed the shape of the answer

04-06 landed a durable shadow certificate and a receipt-gated fast path. A comparison is skipped
only against a certificate that matches on **all four** identities — the Bronze snapshot id, the
Silver snapshot id, the runtime identity (`mode` / `GOLD_SOURCE` / `SHADOW_COMPARE`) and the
projection contract identity — *and* whose recorded `result` is `"equal"`. Every other input,
including no certificate at all, runs the full comparison. Both snapshot reads are table metadata
only, so declining to scan never costs a scan.

The consequence for this decision is precise, and it is the reason the question is worth reopening
at all: **a cycle over unmoved Bronze and unmoved Silver, under an unchanged runtime and an
unchanged projection contract, now performs no Bronze pin, no legacy rebuild and no comparison.**
The cost of validation therefore falls only on cycles that have new state — which are exactly the
cycles where validation has something to find.

The standing cost objection has not been refuted. It has been **relocated**: it no longer applies
to idle cycles at all, and what remains of it applies only where the check is doing work.

> *Claim resting on code and tests rather than on observed data:* that the fast path elides the
> work on a live catalog is established by the unit and BDD suites and by `ci-m5-gates`, not by a
> measurement of a production steady state. No before/after benchmark of the fast path exists yet;
> that is `04-09`'s subject and it has not run.

---

## Options

All four locked candidates, against the same criteria.

### A. Permanent shadow — validation runs whenever persisted Silver is the Gold source

**Cost.** Zero on cycles where the certificate holds. On cycles where Bronze, Silver, the runtime
or the projection contract moved: one Bronze pin, one full legacy projection, one keyed
comparison. At demo volume the shadow phase measured 21–45 s on the cycles that ran it; the
scaling of that number is unknown.

**Detects.** Any divergence between the legacy logical projection and the persisted B2 Silver, for
the exact state that is about to be published, over the whitelisted business columns — before Gold
is written. Because the certificate's identity covers the projection contract, adding or
reclassifying a Silver column invalidates every outstanding certificate and forces a fresh
comparison rather than inheriting a stale verdict.

**Stops detecting.** Nothing within that boundary. It is worth being explicit about what the
boundary excludes in every option: shadow comparison does not validate Bronze itself, and it does
not validate the Gold aggregation — that is `gold_equivalence` in the cutover gate, a separate
check.

**Rollback.** Unaffected. Preserves every rollback path (see *Rollback*, below).

### B. Change-triggered shadow — compare only when the cycle appears to have changed something

**Cost.** Similar to A in the good case; the saving over A exists only where A would have compared
something that a trigger heuristic decides is uninteresting.

**Detects.** Whatever the trigger admits.

**Stops detecting.** Whatever the trigger misses — and the trigger is the whole risk. A heuristic
such as "compare when `work_completed > 0`" is a statement about the *writer's* view of its own
work, not about whether the state being published is the state that was last certified. Silver
moves independently through B2 recovery; Bronze moves through ingestion.

**This option is already implemented, in a strictly better form.** The receipt-gated fast path is
change-triggered validation whose trigger is **proven state identity** — four snapshot-and-contract
identities plus a passing prior result — rather than a heuristic about work. B is therefore not an
alternative to A; it is a weaker way of building what A already does. It is rejected on that basis
rather than on cost.

### C. Sampled or periodic shadow — compare one cycle in N, or one every T

**Cost.** Lower than A only on cycles that changed state, because the fast path has already
removed the cost on cycles that did not. Sampling therefore buys its saving precisely where the
check has something to find.

**Detects.** Divergence, eventually, with unbounded latency.

**Stops detecting.** Divergence in the unsampled cycles, at the moment it matters. Silver is a
**current-state** projection, not an append-only log: a wrong value published in an unsampled
cycle can be overwritten by a later correct one, so a subsequent sampled comparison may pass while
incorrect Gold was published and served in between, with nothing left to find. Sampling is a
reasonable design for detecting *persistent* drift. This gate exists to stop *individual*
publications, and sampling cannot do that by construction.

**Rollback.** Formally unaffected, but materially weakened: rollback is triggered by shadow
failure, and a sampled gate delays the trigger by up to its own period.

### D. Shadow disabled after a certified cutover

**Cost.** Zero, always.

**Detects.** Nothing. After the certifying cutover, business state is published from persisted
Silver with no check that it matches the projection it is supposed to equal.

**Stops detecting.** Everything the gate exists for, permanently, from the moment it is switched
off — including regressions introduced by later changes to B2, to the projection contract, or to
recovery paths, none of which the original certification observed.

**Rollback.** This is the decisive objection. The M5 rollback triggers are *"shadow comparison
fails, progress remains unresolved, FF-14 appears, Gold equivalence is lost, or recovery evidence
is stale/missing."* With shadow disabled, the first of those can never fire. Rollback remains
mechanically possible and nothing tells you to perform it.

**It also requires a forbidden configuration.** `(b2, persisted_silver, 0)` is not in
`RUNTIME_ROLLOUT_MATRIX` and `validate_runtime_config` refuses to start with it.

---

## Decision

**Shadow validation is mandatory for as long as persisted Silver is the Gold source.** Option A.

The precision matters and the informal phrasing lost it. The policy is **not** "`SHADOW_COMPARE`
is `1` forever". The matrix already accepts `("b2", "legacy", "0")` — B2 Silver retained,
validation off, Gold served from the legacy projection — because in that state persisted Silver is
not what is being published. The rule is conditional, and stated correctly it is:

> Whenever `GOLD_SOURCE=persisted_silver`, `SHADOW_COMPARE` SHALL be `1`.

The reasoning, in the order the evidence supports:

1. **The cost objection no longer applies where it used to.** With the receipt-gated fast path, an
   unchanged cycle does no validation work at all. What remains is validation on cycles that
   changed state, which is where a correctness gate belongs.
2. **The alternatives that save more, save it in the wrong place.** C's saving falls entirely on
   the cycles that changed something; D's saving is total and so is its blindness.
3. **B is not an alternative.** Its intent is already realised, by identity rather than heuristic.
4. **Rollback depends on the signal.** Three of the five M5 rollback triggers are only observable
   while comparison runs.

`RUNTIME_ROLLOUT_MATRIX` **is not changed by this ADR.** It holds exactly four keys, and this
change strengthens the assertion that it holds exactly those four rather than relaxing it. In
particular `(b2, persisted_silver, 0)` — persisted Silver as the Gold source with validation
disabled — **remains forbidden** and is not to be added.

### What would have to happen before that could be revisited

Adding `(b2, persisted_silver, 0)` requires a superseding ADR that records the conditions below as
**met, with evidence**, and it requires a named decider; `.planning/STATE.md` and this record both
currently show *(unassigned)*, so assigning one is itself a precondition. No amount of green CI
substitutes for that: the matrix is the enforcement point for a policy, and changing it is an
architectural decision, not a configuration change.

---

## Evidence and safety conditions

These are the preconditions for *proposing* a change to this policy. They are written to be
checkable, so that a future proposal can be judged rather than debated.

| # | Condition | Checkable form |
|---|---|---|
| **C1** | The cost is measured, not estimated | A before/after benchmark of the fast path exists (`04-09`'s subject) **and** a cost relationship is established between the shadow phase duration and the work done — rows, keys and files processed — rather than a single-volume order of magnitude. A five-cycle demo window does not satisfy this and never will, at any number of repetitions |
| **C2** | The measurement covers a realistic volume | At least one order of magnitude above the demo dataset, with the volume stated, and with the fast path enabled so that the figure describes the system as it actually runs |
| **C3** | A continuous clean window, with no gaps | Zero `shadow_mismatches` and zero `ff14_conflicts` across a stated continuous window, expressed in cycles **and** in wall-clock time, with metric coverage proven complete for that window — a gap in the metrics is not a clean window, it is an unobserved one |
| **C4** | Recovery has been drilled inside that window | The writer-crash and retention-recovery drills executed within the window and green, not inherited from an earlier release |
| **C5** | Rollback has been rehearsed, not merely believed | An actual `GOLD_SOURCE=legacy` rollback performed on the deployment in question, with Gold equivalence re-verified afterwards. `rollback_verified` in the cutover evidence bundle is the existing shape of this claim |
| **C6** | Loss of the signal is itself alarmed | An alert fires on `shadow_mismatches > 0` **and** an alert fires on the *absence* of comparisons over a stated interval, each demonstrated to fire in a test. Without the second, "no mismatches" is indistinguishable from "no checking" |
| **C7** | The decision has an owner | A named decider on the superseding ADR |

**Could these be expressed as an evaluable bundle?** Yes, and the precedent exists.
`evaluate_cutover_gate(config, evidence)` in `iceberg/common/cutover.py` is a pure function that
turns a configuration and an evidence mapping into `passed`, a per-check breakdown and a
`failed_checks` list, so CI, an operator or a deployment job can reach the same verdict from the
same inputs. C1–C7 have the same shape: each is a boolean over collected evidence. C3 and C6 would
need evidence fields that do not exist today — a window descriptor with a coverage claim, and an
alert-fired-in-test attestation.

**This ADR does not build such an evaluator.** Building one now would be implementing a gate for a
change nobody has proposed, and this record is analysis. It is noted here so that a future
proposal starts from the existing pattern rather than inventing one.

---

## Rollback

The chosen policy preserves the M4 and M5 rollback definitions exactly.

M4 defines rollback as changing **only** `GOLD_SOURCE` back to `legacy`: it does not reset Silver,
alter B2 progress, or recreate completed Bronze outbox work. M5 adds that `SILVER_MODE=b2` is kept
while B2 Silver is healthy, and that `SILVER_MODE=legacy` is the broader emergency rollback.

Traced through the matrix, every one of those states is already accepted:

| Situation | `SILVER_MODE` / `GOLD_SOURCE` / `SHADOW_COMPARE` | Matrix name |
|---|---|---|
| Cutover deployment, this policy in force | `b2` / `persisted_silver` / `1` | `cutover` |
| Standard rollback — Gold source only | `b2` / `legacy` / `1` | `shadow` |
| B2 Silver retained, validation stood down, Gold on legacy | `b2` / `legacy` / `0` | `rollback` |
| Broader emergency rollback | `legacy` / `legacy` / `0` | `legacy` |

A rollback from `cutover` therefore lands in `shadow`, a state the matrix already accepts and one
in which validation continues to run. **The policy costs rollback nothing**: it neither adds a step
nor removes a destination. It is the option that *preserves* rollback, because the standard
rollback trigger is the shadow signal itself.

---

## Consequences

- The steady-state question has a written answer with conditions attached, so a future proposal
  has something to be measured against and this record can be shown to be wrong.
- `RUNTIME_ROLLOUT_MATRIX` becomes exactly assertable: a fitness test now pins its four keys and
  their four rollout names, so a fifth key fails a test rather than arriving unnoticed. Partial
  coverage was the practical risk behind POL-01 — the existing tests rejected the one forbidden
  combination and would not have noticed any other addition.
- Validation cost is now a function of change rather than of time. The operational consequence is
  that a *sustained absence* of shadow comparisons is no longer evidence of a problem — it is the
  expected steady state — which is precisely why condition **C6** requires alerting on the absence
  of comparisons before any relaxation could be proposed.

## Non-goals — what this ADR does not decide

- It does not decide anything about **Gold's** execution model. ADR-0001 D-4 and its post-Phase-4
  amendment own that, and neither is touched here.
- It does not measure the fast path. `04-09` owns the before/after benchmark, and it has not run;
  every cost claim above is therefore either the frozen five-cycle window or a statement about
  code paths, marked as such where it is made.
- It does not build the C1–C7 evaluator, and it does not add the evidence fields C3 and C6 would
  need.
- It does not change `SHADOW_CONTRACT_VERSION`, the certificate format, or any runtime behaviour.
  Nothing under `iceberg/` is modified by this decision.

---

## Related measurement

Where the remaining per-cycle time goes at the Arrow/Python boundary is measured
separately in
[`artifacts/phase-04/04-arrow-boundary-profile.json`](../../artifacts/phase-04/04-arrow-boundary-profile.json),
produced by `scripts/profile_arrow_boundary.py` under PRF-01. That profile and
this policy are the phase's two answers to the cost question — this one about
work the cycle can decline, that one about work it still performs. Neither
changes the other's conclusion.
