## Context

See proposal.md — Why. Three constraints shape the approach.

**The decision is computed, not chosen.** 01-07's gate defines each outcome as a
conjunction over the collected artifacts. The work here is to evaluate those
conjunctions against `06-telemetry-gate.json` and `06-o1-summary.json` and record
the result with its inputs, not to weigh the options.

**The evidence is frozen and dated.** The O1 window is from 2026-08-10 and
nothing in this change reproduces or extends it. Every figure recorded is read
from a committed artifact, and every artifact is hashed so a reader can tell
whether the record still describes the files it was computed from.

**`.planning/` is no longer a live queue.** The source plan's Task 2 instructs
updating `.planning/STATE.md` and `.planning/ROADMAP.md` as project state. Since
the 2026-08-18 cutover, `engineering-governance` treats those files as
historical evidence, editable only as a migration ledger. That contradiction is
resolved in favour of the governance spec and recorded as a deviation — see
*Decisions*.

## Goals / Non-Goals

**Goals:**

- Exactly one DEC-01 outcome, durably recorded with its inputs and its rejected
  alternatives.
- A record that a later reader can use to decide whether D-3a or O2 has become
  proposable, rather than one that forecloses the question.

**Non-Goals:**

- Any D-3a or O2 work. Not a layout change, not a tracing span, not a
  measurement designed to open either.
- Re-running or extending the O1 window. A one-cycle window is what exists; the
  decision is recorded against it, limits and all.
- Reconciling SPIKE-2's read-fraction figures with O1's planned-vs-added ratios.
  They are different quantities; see *Decisions*.

## Decisions

**The outcome is `no_change`, and it is reached by elimination on stated
conditions rather than by preference.**

`open_d3a` requires three conditions together: a passing telemetry gate,
*repeated* non-empty B2 cycles in the window, and material scan/write
amplification. The first holds. The second fails on the artifact's own count —
`non_empty_b2_rows: 1`. The third fails independently: `files_planned_per_added`
is 1.0 and `bytes_planned_per_added` is 1.028611, with both removal ratios at
0.0, which is the absence of amplification rather than a small amount of it.
Two independent disqualifiers, either sufficient.

`open_o2` requires a real anomalous behaviour that the captured fields cannot
diagnose. The window records none: `validity_reasons` is empty, shadow
mismatches and FF-14 conflicts are zero, final in-flight work is zero, all
required fields are present, and the Prometheus correctness series is present.
There is no anomaly, so there is nothing for tracing to explain.

`no_change` is the outcome for "amplification is not material, or O1 is
sufficient". Both hold.

**The SPIKE-2 comparison is recorded as a caveat, not performed as arithmetic.**
The plan's wording — material amplification "relative to the documented SPIKE-2
baseline" — presumes the two measurements are commensurable. They are not.
SPIKE-2 reports the fraction of the table touched by a read (day: 10 files,
25.00%; bucket: 27 files, 4.22%). O1 reports planned bytes and files against
those *added* by one write. A ratio of scan locality and a ratio of write
amplification do not share a denominator, and dividing one by the other would
manufacture a number with no referent. The receipt therefore names both figures,
states that they are not compared, and rests the `open_d3a` rejection on the
repeatability condition, which is decided by a count and needs no baseline at
all. Alternative considered: normalise the two into a common ratio. Rejected —
it would be an invented quantity presented as a measurement.

**`.planning/ROADMAP.md` is not edited; `.planning/STATE.md` is edited only as a
ledger.** The source plan's Task 2 predates the cutover. Its intent — that the
recorded outcome be traceable from project state — is satisfied by the ledger
entry pointing at this change, which points at the receipt. Editing ROADMAP.md
to reflect a decision made after the freeze would reopen `.planning/` as a live
queue, which `engineering-governance` forbids. The plan's own automated check
for Task 2 asserts that the strings `D-3a`, `O2` and `B2 Controlled Rollout`
appear in those files; they already do, from the pre-freeze history, so the
assertion holds without an edit. That is recorded as a deviation rather than
quietly satisfied.

**Two hashes per evidence artifact.** `sha256` of the working-tree bytes
identifies exactly what was read on this machine; the git blob id identifies the
same content independently of checkout line-ending normalisation. Recording only
the first would produce a receipt that fails to verify on a different platform
for a reason unrelated to the evidence.

## Risks / Trade-offs

- **A `no_change` record is easy to misread as "D-3a and O2 were found
  unnecessary".** → The governance requirement added by this change forbids that
  form, and the receipt carries explicit `reopen_conditions` for each deferred
  item. The outcome is scoped to the evidence and dated.

- **The window is one non-empty cycle.** → Stated at every point the figures are
  used. It is also precisely why `open_d3a` cannot be selected: the plan requires
  repetition, and one cycle cannot demonstrate a repeated pattern. The thinness
  of the evidence argues for the outcome rather than against it.

- **A confirming CI run on `25d240c` was still in flight when this change
  started.** → It exercises the medallion test suites, not the frozen 2026-08-10
  window, so it cannot invalidate the evidence; it is checked before closure
  regardless, and a failure would be classified before the change is archived.

## Migration Plan

None. No runtime behaviour, configuration or schema changes.
