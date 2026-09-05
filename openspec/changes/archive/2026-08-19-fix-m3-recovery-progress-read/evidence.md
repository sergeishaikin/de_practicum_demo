# Evidence — fix-m3-recovery-progress-read

Executed 2026-08-19 on `test/dbt-extensive-testing`. Fix commit `b14dcc2`.

Authorised by the operator on 2026-08-19, for this change only, and explicitly
**without** the `except ValueError` retry that had been proposed alongside it.

## Before-evidence

`H1 clean reproducible stack`, run **32291032255**, SHA `d22b4c1`, job "Fresh
volumes, baked runtime, full verification", failing step "Integration suite":

```text
FAILED tests/integration/test_m3_b2_recovery.py::test_m3_b2_projection_and_crash_recovery
json.decoder.JSONDecodeError: Extra data: line 1 column 515 (char 514)
======= 1 failed, 20 passed, 1 xfailed, 10 warnings in 213.25s (0:03:33) =======
```

The run's `h1-clean-stack-evidence` artifact (256 KB) was downloaded and
confirmed to contain the diagnostic capture directories added by the earlier
diagnosis.

### Not attributable to the commits around it

```bash
git diff --name-only 7d9977d d22b4c1
```

returns nine paths, all under `openspec/` and `docs/`. Nothing executable
changed.

### Intermittency established from CI, not asserted

| SHA | H1 clean stack | Executable difference |
|---|---|---|
| `7d9977d` | pass | — |
| `d22b4c1` | **fail** | none |
| `2ec7376` | pass | none |

### The reader at HEAD before any edit

`git show HEAD:tests/integration/test_m3_b2_recovery.py`, line 116:

```python
with storage.open_input_file(object_path) as source:
    progress = json.loads(source.read().decode("utf-8"))
```

An inventory of `open_input_file(` across `tests/` found the M3 poller to be the
only caller that is neither a test double implementing the filesystem interface
nor the diagnostics module. `tests/support/progress_read_diagnostics.py` calls it
deliberately — reproducing the random-access read is that module's purpose — and
is out of scope. Recorded so a future reader grepping for the defective call
knows it is intentional.

## The change

One call in `wait_for_completed`:

```diff
- with storage.open_input_file(object_path) as source:
+ with storage.open_input_stream(object_path) as source:
```

`except (FileNotFoundError, OSError)` unchanged. Poll interval, deadline and
absence of backoff unchanged.

## Negative proofs

Both mutations were applied to the working tree, run, and reverted. Neither
result is inferred.

| Mutation | Test | Exit | Message |
|---|---|---|---|
| Revert the call to `open_input_file` | `test_the_m3_recovery_poller_is_sequential_too` | **fail** | `assert 'open_input_stream' in '…'` |
| Add `ValueError` to the retry clause — the exact variant proposed and rejected | `test_the_m3_recovery_poller_does_not_swallow_a_decode_failure` | **fail** | `assert 'except (FileNotFoundError, OSError):' in '…'` |
| Restored fix | both | **pass** | `2 passed in 0.63s` |

The second proof is the one worth keeping: the rejected design is now pinned by a
test, so it cannot be reintroduced quietly the next time this flakes.

## Local gates

| Check | Result |
|---|---|
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked black --check .` | 76 files unchanged (the appended tests were formatted first, then re-verified) |
| `uv run --locked pytest tests --cov=iceberg --cov-fail-under=90` | **409 passed**, 70 deselected, coverage **94.29%** |
| Coverage delta | none — `iceberg/` is untouched; 94.29% matches the pre-change figure |
| Deselected delta | 67 → 70, exactly the three added `integration`-marked tests |

### Not run locally, and why

The M3 integration test itself. No live stack is available in this environment
and starting one is not authorised — `AGENTS.md` treats Docker, Kafka, MinIO and
Iceberg as stateful, and this change carries no authorisation to mutate them. Its
proof comes from CI, below.

## Scope fence

```bash
git diff --exit-code iceberg/ dags/ dbt/ spark/ kafka/ observability/ scripts/ \
  .planning/ openspec/backlog/ openspec/specs/ docker-compose.yml \
  docker-compose.extended.yml pyproject.toml uv.lock .github/
git diff --exit-code tests/support/progress_read_diagnostics.py
```

Both exit 0. Only `tests/integration/test_m3_b2_recovery.py`,
`tests/integration/test_progress_read_under_shrink.py` and this change's own
artifacts were modified.

## Live proof — three H1 successes on one SHA

All on `b14dcc2`, with no push between them, so all three ran identical code.

| Run | Trigger | Conclusion |
|---|---|---|
| 32295338891 | `pull_request` | **success** |
| 32295351837 | `workflow_dispatch` | **success** |
| 32295354813 | `workflow_dispatch` | **success** |

The `pull_request` run above was produced on head `b14dcc24` of
`test/dbt-extensive-testing` against base `main@33316ece` (PR #1). The two
`workflow_dispatch` runs are exact-SHA receipts and have no base.

The other three workflows on the same SHA also passed: CI (32295339034), M5
architecture gates (32295338997), S1 dbt semantic lineage (32295338954).

### The integration suite counts corroborate the fix

| | Integration suite |
|---|---|
| `d22b4c1` (before) | 1 failed, 20 passed, 1 xfailed |
| `b14dcc2` (after) | **24 passed**, 1 xfailed |

21 non-xfail tests became 24: the previously failing test now passes, and the
three added tests ran rather than being skipped.

## What this evidence does and does not claim

It claims: the mechanism that explains the observed failure — a read sized from a
stale HEAD across a shrinking overwrite — is no longer present in this reader,
and three subsequent H1 runs on one SHA did not reproduce the failure.

It does **not** claim the test can never fail again. Three green runs raise
confidence; they do not prove the absence of a race, and one occurrence in three
prior runs is a small sample. Only the stale-size mechanism was addressed.

**If this recurs with the same `JSONDecodeError`:** capture the bytes and
classify the failure. Do not add `ValueError` or any broader exception to the
retry clause. After a sequential read there is no stale-size mechanism left to
explain a decode failure, so a recurrence would be a *different* defect, and
absorbing it would convert real corruption into a 90-second timeout reported as
`M3 work … did not complete`.

## Deliberately not done

- No production code touched. `git diff --exit-code iceberg/` is clean.
- No exception type added to the retry clause.
- No timing change: poll interval, deadline and absence of backoff are as they
  were.
- No assertion weakened, no test skipped or xfailed.
- `tests/support/progress_read_diagnostics.py` untouched.
- No other `open_input_file` call site audited or changed — that would be a
  different change with a different fence.
- No NG item started. `add-static-typing-gate` remains unauthorised.
