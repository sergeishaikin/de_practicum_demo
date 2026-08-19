## Context

See proposal.md — Why. The constraint that shapes everything here is that the
evidence needed to classify the failure does not survive the run that produces
it:

- The R1 test starts its streaming container outside compose and then calls
  `docker_rm(stream_name)`. The container and its logs are gone before the
  assertion fails, and the workflow's `Collect logs` step reads compose services
  only — which is why the collected `h1-clean-stack.log` contains Kafka's view of
  the topic but nothing from the process under investigation.
- The workflow's `Destroy clean stack` step removes volumes, so the MinIO
  checkpoint prefix that would answer "did the first process commit anything?"
  is deleted before anyone can look.
- Cold start is only reproducible in this workflow. `verification-contract`
  gives the destructive fresh-volume run exactly one owner, so the evidence has
  to be captured inside it rather than reproduced locally.

## Goals / Non-Goals

**Goals:**

- Capture, from a fresh-volume run, the four facts that separate the three
  candidate classifications.
- Leave the behaviour under investigation untouched, so the captured run is
  evidence about the failure rather than about the instrumentation.

**Non-Goals:**

- Fixing the failure. The remedy belongs to a successor change, whichever
  classification wins.
- Making H1 green. That is a consequence of the remedy, not of this change.
- Deciding the remedy's shape in advance — in particular, this design does not
  assume the harness constants are wrong.

## Decisions

**Capture evidence in the workflow, not in the test.** The obvious route is to
make the R1 helper keep its container or tee its output, but that edits the
harness whose assumptions are the leading hypothesis. Instrumenting the suspect
is how a warm-state bug gets accidentally papered over. Instead the workflow
gains a diagnostic step that runs only when the E2E step fails, reads state that
already exists at that moment, and uploads it. Alternative considered: reproduce
locally with `down -v` — rejected, `verification-contract` assigns fresh-volume
proof to H1 alone.

**The decisive artifact is the checkpoint prefix in MinIO.** If the first
streaming process never wrote a committed offset before it was removed, then
there was no offset to lose, the second run starts from scratch, and the test is
asserting on a precondition it never established — that is the warm-state
classification, proved rather than inferred. If a commit does exist and the
record still never lands, the failure is downstream of the harness and the
classification changes. Alternative considered: infer it from Kafka consumer
group offsets alone — kept as corroboration, but Spark commits offsets to its
own checkpoint, so the checkpoint is the primary source.

**Measure, do not adjust.** The step records how long Spark took from launch to
first committed checkpoint on a cold stack. That number is what a later change
would need to justify any constant, and capturing it now keeps the remedy
evidence-based instead of "raise it until it passes".

**One re-run, then classify.** The captured run either supports a
classification or shows what is still missing. If it shows the latter, that is
recorded as the outcome of this change rather than answered by widening the
investigation until something turns up.

## Risks / Trade-offs

- **The diagnostic step is itself untested until H1 runs.** It is written to be
  best-effort and `if: failure()`-scoped so it cannot turn a green run red; if it
  errors, the run's own outcome is unchanged and we have learned nothing rather
  than broken something.
- **The failure may not reproduce.** A timing-dependent failure can pass on the
  next run. That outcome is informative — it moves the classification toward CI
  orchestration and timing — and must be recorded rather than treated as
  resolution.
- **Cost.** Each H1 run is a full clean rebuild of up to 180 minutes. This design
  spends one deliberately, which is why it captures all four facts at once
  instead of one per iteration.
- **Evidence retention.** The artifact upload keeps the captured state for the
  successor change; without it the next person repeats this run.
