## Context

See proposal.md — Why. Three facts about the current repository shape the
approach.

**There is no denominator.** `artifacts/phase-04/` does not exist. The plan's
Branch B expects a refusal receipt to quote; there is none, because `04-09` was
never authorised and therefore never ran far enough to write one. The adaptation
is stated in the proposal and recorded again in the artifact itself.

**The production call sequence is not what a naive reading suggests.** At
`iceberg/medallion/iceberg_medallion.py:621` the cycle calls
`collapse_delta(incoming)`, and at line 630 it calls
`resolve_against_current(current, incoming)` — which calls `collapse_delta` on
the same `incoming` a second time. The boundary therefore collapses the delta
twice per cycle. This is correctness-neutral, since `collapse_delta` is pure and
deterministic, but it is real work, it is invisible in a reading of the four
steps as a list, and it has to be reported as its own quantity rather than left
folded into `resolve_against_current`.

**The recorded production delta is tiny.** Across the entire committed evidence
base the largest observed B2 cycle processed one key, one file, 4,422 bytes
(`artifacts/b2-rollout/06-o1-window.json`). Any measurement at 10^4 or 10^6 rows
is a statement about a regime this pipeline has never been observed in.

## Goals / Non-Goals

**Goals:**

- The four boundary steps measured separately, at four or more delta sizes
  spanning four or more orders of magnitude, as medians over repeats.
- A recorded disposition with the reasoning and the flip point, so a future
  reader can reopen the question with evidence rather than intuition.

**Non-Goals:**

- Optimising anything. `OPTIMISE` is unreachable without a denominator, and the
  authorisation forbids touching `iceberg/` regardless.
- Fixing the double collapse. It is measured and reported; changing it is
  production code and belongs to a separate authorisation.
- Reproducing production conditions. A synthetic microbenchmark cannot, and the
  artifact says so beside its numbers rather than in a footnote.

## Decisions

**Measure the four steps and the executed sequence, not only the steps.**
The profile records both: the four named steps the plan asks for, and a
`production_sequence` measurement reproducing lines 609-630's call order.

*Corrected after measuring.* This decision was first written on the reasoning
that summing the four steps would **understate** the executed cost, because the
sequence collapses the delta twice. That reasoning was wrong: the separately
measured `resolve_against_current` already includes its own internal collapse, so
the sum covers both collapses too. The measurements confirm it — sum and sequence
agree within 8% at every size, and at 10^6 the sum is the larger of the two.

The sequence measurement is kept for a different and weaker reason: it is the
only figure that corresponds to something a cycle actually executes end to end,
and it independently confirms that the per-step sum is not an artefact of
measuring in isolation. The double collapse remains real and is reported as its
own finding, quantified as `collapse_delta_ms` against the sequence total.

**Synthetic rows, generated to a stated key cardinality and overlap ratio.** The
cost of steps 2 and 3 depends on how many distinct keys a delta carries and how
many of them already exist in current state, so both are parameters and both are
recorded per measurement. Payloads are deterministic per `(order_id, version)`
so that no accidental FF-14 conflict is generated — the conflict path is a
raise, and measuring a raise instead of the resolution loop would be measuring
the wrong thing.

**Medians over repeats, with the repeat count recorded.** A single sample of a
sub-millisecond operation on a shared machine is noise. Repeat counts scale down
with size so the largest sweep stays bounded in wall time.

**No pytest marker, no benchmark plugin.** `AGENTS.md` forbids adding a
verification layer the change does not require, and `scripts/` already holds
one-off JSON-emitting tools — `verify_m5_cutover.py` is the precedent this
follows in shape: `main()`, `argparse`, JSON to a path, nothing decorative.

**The disposition is chosen by a rule fixed before the numbers are read.**
Branch B allows two terminal values. `NOT WORTH DOING (unmeasurable baseline)`
requires the measured boundary cost to be negligible **in absolute terms at every
delta size the pipeline has actually been observed to produce** — that is, at the
recorded production delta of one key. `INCONCLUSIVE` is the value if it is not.
The rule is written here, in advance, so the choice cannot be fitted to the
result.

## Risks / Trade-offs

- **A microbenchmark can be read as a production prediction.** → The artifact
  carries an explicit limits block naming what it does not reproduce: cache
  behaviour under a real scan, real payload distributions, and the Arrow buffer
  layout a catalog read produces. It bounds the cost; it does not predict it.

- **The 10^6 sweep costs minutes of CPU and significant memory.** → Repeat counts
  are reduced at the largest sizes, and the sizes are parameters rather than
  constants so a reviewer can re-run a cheaper sweep. The run is local and
  touches no service.

- **The double-collapse finding invites an immediate fix.** → It is out of scope
  by authorisation, and the fix would need `iceberg/` changed. It is recorded in
  the artifact as a finding with its measured cost, and carried to a separate
  authorisation. This change stops rather than widens.

## Migration Plan

None. No runtime behaviour, configuration or schema changes.
