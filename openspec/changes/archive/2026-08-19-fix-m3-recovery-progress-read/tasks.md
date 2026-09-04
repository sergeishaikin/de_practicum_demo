## 1. Before-evidence

- [x] 1.1 Capture the `d22b4c1` failure: run `32291032255`, job "Fresh volumes, baked runtime, full verification", failing step "Integration suite", `JSONDecodeError: Extra data: line 1 column 515 (char 514)` in `test_m3_b2_projection_and_crash_recovery`, `1 failed, 20 passed, 1 xfailed in 213.25s`
- [x] 1.2 Download the run's `h1-clean-stack-evidence` artifact and confirm the capture harness from the earlier diagnosis was present
- [x] 1.3 Prove the failure is not attributable to the commits around it: `git diff --name-only 7d9977d d22b4c1` returns only `openspec/` and `docs/` paths
- [x] 1.4 Establish intermittency from CI rather than assertion: `7d9977d` pass, `d22b4c1` fail, `2ec7376` pass, with no executable difference between them
- [x] 1.5 Prove the helper still uses `open_input_file` at HEAD before any edit: `git show HEAD:tests/integration/test_m3_b2_recovery.py`, line 116
- [x] 1.6 Inventory every `open_input_file(` in `tests/`; confirm the only non-fake, non-diagnostic caller is the M3 poller

## 2. Reuse before writing

- [x] 2.1 Read `tests/integration/test_progress_read_under_shrink.py` in full — the file that already owns this defect class, with LARGE/SMALL payloads bracketing the observed 236-byte boundary and a source assertion on the writer's reader
- [x] 2.2 Read the production remedy `medallion._read_json` and match its form exactly rather than inventing a variant
- [x] 2.3 Confirm `tests/support/progress_read_diagnostics.py` uses `open_input_file` deliberately — reproducing the random-access read is its purpose — and record that it is out of scope

## 3. The fix

- [x] 3.1 `wait_for_completed`: `open_input_file` → `open_input_stream`. One call
- [x] 3.2 Leave `except (FileNotFoundError, OSError)` exactly as it was; add no exception type
- [x] 3.3 Leave the one-second poll and the 90-second deadline untouched; add no backoff
- [x] 3.4 Docstring recording why the read is sequential and why a decode failure is deliberately not retried

## 4. Regression

- [x] 4.1 `test_the_m3_recovery_poller_is_sequential_too` — source assertion mirroring the existing writer test
- [x] 4.2 `test_the_m3_recovery_poller_does_not_swallow_a_decode_failure` — the retry clause absorbs exactly `(FileNotFoundError, OSError)` and rejects `ValueError`, `JSONDecodeError`, `UnicodeDecodeError` and bare `Exception`
- [x] 4.3 `test_a_malformed_object_still_raises_through_the_sequential_reader` — behavioural: a truncated document raises `JSONDecodeError` through the same reader the poller uses
- [x] 4.4 Negative proof A: revert the helper to `open_input_file`, run 4.1, record that it fails and with what message; restore
- [x] 4.5 Negative proof B: add `ValueError` to the retry clause — the exact variant that was proposed and rejected — run 4.2, record that it fails; restore
- [x] 4.6 Confirm the restored helper is byte-identical to the intended fix and both tests pass

## 5. Gates

- [x] 5.1 `uv run --locked ruff check .`
- [x] 5.2 `uv run --locked black --check .`; format the appended tests and re-verify
- [x] 5.3 `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90`; confirm coverage is unchanged, this being a test-only change
- [x] 5.4 Confirm the deselected count rose by exactly the three added integration tests
- [x] 5.5 `git diff --exit-code iceberg/` and the rest of the fence
- [x] 5.6 Record that the M3 integration test could not be run locally — no live stack is available and starting one is not authorised — and that its live proof comes from CI

## 6. Live proof

- [x] 6.1 Commit and push
- [x] 6.2 Confirm all four workflows on the pushed SHA
- [x] 6.3 Because the defect is intermittent, obtain **three** `H1 clean reproducible stack` successes on the **same** SHA, dispatched without pushing in between
- [x] 6.4 If any of the three fails with the same `JSONDecodeError`: do not close the change, do not add `ValueError`; capture the bytes and classify the new failure
- [x] 6.5 Record the three run ids and their conclusions

## 7. Closure

- [x] 7.1 Write `evidence.md`: before-evidence, both negative proofs with their messages, gate figures, the three H1 receipts, and the bounded form of the claim
- [x] 7.2 Archive the change; push the archive
- [x] 7.3 Verify: zero active OpenSpec changes, clean working tree, backlog still fourteen items `Authorised: no`
- [x] 7.4 Stop. Completing this authorises nothing; `add-static-typing-gate` needs its own decision
