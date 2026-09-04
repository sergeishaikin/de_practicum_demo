## 1. ADR-0002 — steady-state shadow policy

- [x] 1.1 Read the sources the decision rests on: `docs/adr/0001-incremental-silver-and-gold.md` (header table, D-4, the post-Phase-4 amendment), `iceberg/common/cutover.py` in full, `docs/remediation/M4-shadow-gold-cutover.md` and `M5-fitness-functions-and-cutover-gates.md`, the certificate and fast path in `iceberg/medallion/iceberg_medallion.py`, `04-CONTEXT.md` §P2, and the recorded decision in `.planning/STATE.md`
- [x] 1.2 Write `docs/adr/0002-steady-state-shadow-policy.md` with ADR-0001's header table fields (Status, Date, Deciders, Supersedes, Evidence base)
- [x] 1.3 Context section: state the question precisely, why it was ever a question, the measured cost from `artifacts/b2-rollout/06-o1-window.json` with its limits stated inline, and what the receipt-gated fast path changed about the argument
- [x] 1.4 Options section: evaluate permanent shadow, change-triggered shadow, sampled/periodic shadow, and shadow-disabled-after-certified-cutover — each with its cost, what it detects, what it stops detecting, and its effect on rollback
- [x] 1.5 Conditions section: state as checkable preconditions what would have to be true before any move away from the policy could be proposed — evidence, window, volume, recovery drills, rollback rehearsal, alerting — and say whether they could be expressed as an evaluable bundle in the style of `evaluate_cutover_gate`, without building one
- [x] 1.6 Decision section: state the answer and its reasoning; state that `RUNTIME_ROLLOUT_MATRIX` is not changed by this ADR; name `(b2, persisted_silver, 0)` as forbidden; say what would have to happen, and who decides, before that could be revisited
- [x] 1.7 Rollback section: show the M4 rollback definition survives — rollback changes `GOLD_SOURCE` only and returns a cutover deployment to the `shadow` state the matrix already accepts
- [x] 1.8 Consequences and non-goals, including what this ADR does not decide; mark every claim that rests on reading code rather than observed data at the point of the claim
- [x] 1.9 Verify: `git diff --exit-code iceberg/` and `git diff --exit-code docs/adr/0001-incremental-silver-and-gold.md` are both clean

## 2. Pin the rollout matrix exactly

- [x] 2.1 Read `tests/test_m5_fitness_functions.py` around the two existing rollout tests, `iceberg/common/cutover.py` lines 19-27, and `tests/features/shadow_cutover.feature` lines 17-32
- [x] 2.2 Add one `@pytest.mark.architecture` test asserting `RUNTIME_ROLLOUT_MATRIX` equals exactly the four accepted keys mapped to `legacy`, `rollback`, `shadow` and `cutover`, docstringed with why equality rather than membership
- [x] 2.3 Negative proof: temporarily add a fifth key to `RUNTIME_ROLLOUT_MATRIX`, run the new test, record that it failed and with what message
- [x] 2.4 Revert the temporary key and confirm `git diff --exit-code iceberg/common/cutover.py` is clean
- [x] 2.5 Confirm the two pre-existing rollout tests are unchanged and still pass

## 3. Gates and closure

- [x] 3.1 Run `uv run --locked ruff check .`, `uv run --locked black --check .`, `uv run --locked pytest`, and the coverage gate `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90`; record the figures each returned
- [x] 3.2 Run `uv run --locked pytest -q tests/test_m5_fitness_functions.py -m architecture` and record the count
- [x] 3.3 Write `evidence.md` in this change: the negative proof, the gate figures, and any place where a source artifact's description did not match the code
- [x] 3.4 Commit atomically, push, and confirm the repository gates are green in live CI on the pushed SHA
- [x] 3.5 Record the migration outcome for `04-08` in `.planning/STATE.md` as a ledger entry only, and stop — `04-09` is not begun
