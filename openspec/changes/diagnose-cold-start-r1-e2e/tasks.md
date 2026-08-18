## 1. Capture the evidence a failing run currently destroys

- [x] 1.1 Add a diagnostic step to `.github/workflows/ci-h1-clean.yml` that runs `if: failure()` after `Deterministic E2E`, before the stack is destroyed, and is best-effort so it can never change the run's own outcome
- [x] 1.2 In that step, list the MinIO checkpoint prefix for the R1 run — whether `offsets/` and `commits/` exist, and which epochs — since a committed offset from the first process is the fact that separates the classifications
- [x] 1.3 In the same step, dump Kafka consumer-group offsets and the topic's earliest/latest offsets and high watermark, as corroboration of the checkpoint reading
- [x] 1.4 In the same step, capture any streaming container still present (`docker ps -a`, and its log if the container survives) so the ad-hoc process is no longer invisible
- [x] 1.5 Record Spark launch → first committed checkpoint latency on the cold stack, so any later argument about a constant has a measured number behind it — captured only as far as existing state allows: checkpoint object timestamps from `mc ls` against container `CreatedAt`. If that does not yield a latency, the classification records `not observable with current evidence` rather than instrumenting the R1 test
- [x] 1.6 Extend the artifact upload to include the captured evidence, so the successor change does not have to re-run H1

## 2. Produce a failing run under observation

- [ ] 2.1 Push the diagnostic step and let H1 run on a fresh volume
- [ ] 2.2 If the E2E step fails, download the artifact and record the four facts verbatim in `evidence.md` in this change
- [ ] 2.3 If the E2E step passes, record that the failure did not reproduce, with the run id and timing, and treat non-reproduction as evidence rather than as resolution

## 3. Classify

- [ ] 3.1 Decide which of the three the evidence supports: an invalid warm-state assumption in the harness, a Spark/Kafka cold-start correctness defect, or CI orchestration and timing
- [ ] 3.2 State the reasoning against each classification that was rejected, not only for the one chosen
- [ ] 3.3 If the evidence supports none of them, record that as the outcome and name exactly what is still missing — do not widen the investigation to force a verdict
- [ ] 3.4 Name the successor change that will carry the remedy, and state explicitly that no remedy was applied here

## 4. Close

- [ ] 4.1 Confirm the scope fence held: no timeout raised, no sleep lengthened, no retry added, no checkpoint reset, no assertion weakened, no production Kafka or Spark semantics changed
- [ ] 4.2 Update `.planning/STATE.md`'s migration row for this obligation with the classification outcome, since that table is where a reader looks for what happened to it
