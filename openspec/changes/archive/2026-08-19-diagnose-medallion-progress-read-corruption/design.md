## Context

See proposal.md — Why.

**The control experiment is already done.** M5 was re-run exactly once on
`7c4c7c7`, the commit immediately before the first failure, and passed. On
`a576c31` it has failed twice, at two different steps. `a576c31`'s diff touches
only `artifacts/`, `docs/`, `openspec/` and `scripts/`, none of which the M5
gates import, so it cannot reach these tests. The correlation is observed; the
cause is not established, and a green control does not make `a576c31` an
explanation.

**Concurrent writers are ruled out by reading the test.** Each run uses a unique
`progress_path` of `m4/{run_id}/progress.json`, and the first medallion process
is terminated before the second starts. One writer, one reader polling once a
second.

## Goals / Non-Goals

**Goals:**

- Establish where bytes that were never written come from, to the point of a
  named class rather than a plausible story.
- Leave behind evidence that a second occurrence can be compared against.

**Non-Goals:**

- Making the failing read succeed. A corrupted read must stay a failure.
- Any change to `iceberg/` before the cause is established.
- Revisiting `04-10`'s disposition.

## Decisions

**Capture, then re-raise.** The diagnostics module raises
`ProgressReadCorruption` in place of the decode error, carrying the evidence
path. The test still fails. This is the distinction the authorisation draws:
capturing evidence at the moment of failure is required, retrying past it is
forbidden.

**The undecoded bytes are written first** — before the second read, before the
report, before anything that could itself raise. A capture that loses the bytes
while trying to describe them is worthless.

**Two comparisons discriminate the hypotheses**, and they are why this
instrumentation is worth a CI round trip:

- *A second independent read of the same object.* If it parses, the stored object
  is intact and the fault is in the first read. If it fails identically, the
  object on the server is genuinely corrupt.
- *A read through `open_input_stream` rather than `open_input_file`.* The former
  is sequential; the latter is random-access and sizes itself from a HEAD. If the
  sequential read returns the object and the random-access read returns the
  object plus a tail, the fault is in how the size is obtained or applied, not in
  what was stored.

Together they separate the classes: object written corrupt (A), read returns
extra bytes (B), reader sees an inconsistent version mid-overwrite (C), harness
lifecycle (D).

**No production instrumentation yet.** The medallion's own `_read_json` has the
same shape, but adding capture there would edit `iceberg/` before the cause is
known. The test-side capture observes the same object, written by the same
writer, which is sufficient to classify.

## Risks / Trade-offs

- **The fault may not reproduce with instrumentation attached.** → Then the
  capture is dormant and costs nothing, and the change records the cause as **not
  established** rather than inventing one. That is an honest terminal state for a
  diagnostic change, and the instrumentation stays for the next occurrence.

- **The capture writes into `artifacts/`, which is gitignored.** → The CI upload
  step covers the CI case, which is where the failure occurs. Nothing about the
  capture depends on those files being tracked.

- **A second read is itself a read of a moving object.** → Deliberately. If the
  object is mid-overwrite, a second read taken milliseconds later is exactly the
  observation that distinguishes a transient inconsistency from stored
  corruption. Its own size and digest are recorded so the two are comparable.

## Migration Plan

None yet. No behaviour changes until the classification is made.
