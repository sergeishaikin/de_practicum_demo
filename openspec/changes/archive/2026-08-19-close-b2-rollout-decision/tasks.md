## 1. Compute and record the DEC-01 decision

- [x] 1.1 Read the decision inputs: `05-cutover-receipt.json`, `06-o1-window.json`, `06-o1-summary.json`, `06-telemetry-gate.json`, `06-o1-prometheus.json`, `06-bounded-workload.json`, and `docs/spikes/SPIKE-2-b2.md`
- [x] 1.2 Evaluate each outcome's stated conditions against those artifacts and record which condition decided it, not merely which outcome won
- [x] 1.3 Write `artifacts/b2-rollout/07-rollout-decision.json`: exactly one `outcome`, `rejected_outcomes` equal to the other two, `implementation_changes: []`, evidence entries with path plus both hashes, gate statuses, measured ratios, runtime disposition, rollback status, per-item `reopen_conditions`, and the SPIKE-2 non-comparability caveat as a field rather than as prose only
- [x] 1.4 Write `artifacts/b2-rollout/07-rollout-result.md` with the same ledger in reviewable form, including why each rejected outcome was rejected and what would have had to be true instead
- [x] 1.5 Verify the schema and scope fence: `outcome` in the allowed set, `rejected_outcomes` exactly the complement, `implementation_changes == []`, `evidence` non-empty

## 2. Traceability without reopening the frozen plan

- [x] 2.1 Confirm the source plan's Task 2 assertion anchors already hold — `D-3a` and `O2` present in `.planning/STATE.md`, `B2 Controlled Rollout` present in `.planning/ROADMAP.md` — so no edit is needed to satisfy them
- [x] 2.2 Record the ledger entry for `01-07` in `.planning/STATE.md`, naming the outcome and this change; leave `.planning/ROADMAP.md` unedited and record that as a deviation from the pre-cutover plan
- [x] 2.3 Confirm no evidence artifact was modified: `git diff --exit-code artifacts/b2-rollout/` clean except for the two new files

## 3. Gates and closure

- [x] 3.1 Run the plan's own automated verifications for Task 1, Task 1a and Task 2 and record their output verbatim
- [x] 3.2 Run `uv run --locked ruff check .`, `uv run --locked black --check .`, `uv run --locked pytest`, and the coverage gate; record the figures
- [x] 3.3 Check the confirming CI on `25d240c` before closure; if it produced evidence capable of invalidating the 01-07 inputs, classify it before archiving, otherwise proceed
- [x] 3.4 Write `evidence.md` in this change: the decisive conditions, the verbatim gate output, the deviation, and any discrepancy found between the frozen plan and the current repository
- [x] 3.5 Commit atomically, push, and confirm the repository gates are green in live CI on the pushed SHA
- [x] 3.6 Merge the spec delta, archive the change, and stop — `04-10` is not begun without separate authorisation, and `04-09` is not touched
