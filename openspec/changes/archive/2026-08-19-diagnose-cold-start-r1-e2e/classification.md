# Classification

## Outcome

**Not established.**

The observed run did not reproduce the failure, so the decisive fact this change
was built to capture — whether the first streaming process ever committed an
offset — does not exist for either run. Task 3.3 anticipated this outcome, and
the one-run boundary in design.md forbids buying another 180-minute rebuild
inside this change to chase it.

What the evidence does support is narrower than a classification: the failure is
**timing-sensitive**, not deterministic. Two fresh-volume runs of the same
executable code produced `1 failed` in 349 s and `3 passed` in 206 s. Whatever
the mechanism, it is not "this test cannot pass on a cold stack".

## Against each candidate

**Invalid warm-state assumption in the harness — not refuted, not confirmed.**
The two fixed constants remain the strongest structural suspects: `sleep(20)`
assumes Spark starts *and* commits a checkpoint within 20 s, and the restart
pairs `max_offsets_per_trigger=1` with a 60 s trigger inside a 180 s budget.
Timing sensitivity is exactly how such an assumption presents — it holds on a
fast run and breaks on a slow one. But "consistent with" is not "shown": no run
has yet shown the checkpoint state at the moment `docker_rm` was called. This
stays the leading reading precisely because it explains non-determinism without
requiring a correctness defect.

**Spark/Kafka cold-start correctness defect — weakened, not eliminated.** A
genuine defect in offset-loss detection should not disappear on a faster runner.
Non-reproduction under identical code makes this the least likely of the three.
It cannot be dismissed outright: if the first process *did* commit an offset in
the failing run and the record still never landed, the defect would be real and
the timing merely the trigger. That is the branch the missing evidence would
settle.

**CI orchestration and timing — supported as a contributing factor, insufficient
as the whole answer.** Runner variance is demonstrated: 349 s versus 206 s for
the same suite. But calling it *the* cause would mean claiming the test is
correct and the runner merely slow, and nothing here establishes that. A test
whose pass depends on the runner being fast is a property of the test as much as
of the runner.

## Missing evidence, named exactly

1. The e2e checkpoint tree from a **failing** cold run — specifically whether
   `s3://de-practicum/e2e/<run_id>/checkpoints/raw/commits/` contains an epoch
   at the moment the first streaming container is removed.
2. Kafka consumer-group offsets for that run at the same moment.
3. The ad-hoc `e2e-streaming-<run_id>` container's log from the failing run.
4. Elapsed time from Spark launch to first committed checkpoint on a slow cold
   stack, which no surviving artifact records.

All four are what `Capture cold-start E2E diagnostics` now collects. The step is
in place and unexercised: the next E2E failure produces them without anyone
having to plan for it again. That is what this change leaves behind.

## Successor

`diagnose-cold-start-r1-e2e` applies **no remedy**, and none was applied. No
timeout was raised, no sleep lengthened, no retry added, no checkpoint reset, no
assertion weakened, and no Kafka or Spark semantics changed.

The successor depends on which fact arrives first:

- If a later H1 run fails at E2E, its artifact carries the four facts and a
  classification change can be opened with evidence in hand.
- If the intent is to stop depending on chance, the successor is a change that
  makes the R1 harness state its precondition explicitly — waiting for an
  observable committed checkpoint instead of `sleep(20)` — rather than one that
  enlarges a constant. That is a remedy proposal and needs its own fence.

A fourth, unrelated H1 layer surfaced in the same run (`dbt semantic contract`
failing on `cp: cannot create regular file 'profiles.yml': Permission denied`).
It is recorded in evidence.md and belongs to its own change; it was not
investigated here.
