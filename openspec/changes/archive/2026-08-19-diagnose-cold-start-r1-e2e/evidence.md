# Evidence

## The observed run

Run `32193696670`, event `pull_request`, head `399957b` on `test/dbt-extensive-testing`, base `main@33316ece` (PR #1), fresh volumes.

**`Deterministic E2E` passed.** The failure did not reproduce.

```text
3 passed, 3 skipped in 205.84s
started  2026-08-18T22:47:28Z
completed 2026-08-18T22:50:54Z   (206 s)
```

Compared with the run that produced the failure, `32191257152` on `0dfd479`:

```text
1 failed, 2 passed, 3 skipped in 348.99s
started  2026-08-18T22:16:50Z
completed 2026-08-18T22:22:40Z   (350 s)

FAILED tests/e2e/test_r1_streaming_e2e.py::test_r1_offset_loss_fails_loudly
AssertionError: timed out after 180s waiting for one Kafka record
committed before offset loss (last=False)
```

The same three E2E tests, on the same cold-start path, took 206 s in one run and
350 s in the other, and only the slower one failed. The two commits differ only
by the failure-scoped diagnostic step and planning documents; nothing that
executes during E2E changed between them.

## The diagnostic step captured nothing, and that is correct

`Capture cold-start E2E diagnostics` shows `skipped`. It is `if: failure()`, and
at the point it would have run no step had failed. Two consequences worth
recording rather than rediscovering:

- It captures state only when a step **before it** has already failed. The `dbt
  semantic contract` failure later in this same run did not retro-trigger it.
- It is therefore still unexercised. Its own correctness — MinIO alias, `mc ls`
  paths, the Kafka commands, the container filter — has not been demonstrated by
  a run, only by review.

## Cold-start latency

`not observable with current evidence`.

The design intended to derive it from checkpoint object timestamps against the
streaming container's `CreatedAt`. Those objects live in the MinIO volume that
`Destroy clean stack` removes, and the capture step did not run, so no such
timestamps exist for either run. Deriving them would require instrumenting the
R1 test, which this change's fence forbids.

## An unrelated failure surfaced in the same run

The run is red, but not at E2E:

```text
dbt semantic contract   failure   (started 22:50:54, completed 22:50:55)
cp: cannot create regular file 'profiles.yml': Permission denied
```

One second, on the `cp profiles.yml.example profiles.yml` line, after the venv
sync succeeded. This is a fourth distinct H1 layer, unrelated to R1 and to
anything this change touched — the `dbt/` directory is bind-mounted into
containers on a clean stack, and the runner user could not write into it.

Recorded here as an observation only. Not investigated, not fixed: it belongs to
its own change.

## Also observed

`ci-h1-clean.yml` does not list its own path in the `pull_request` paths filter,
but the workflow still runs on every push to this PR, because a `pull_request`
paths filter is evaluated against the whole PR diff rather than the latest
commit — and this PR already touches `iceberg/**`, `docker-compose*.yml` and
`dbt/**`. The `workflow_dispatch` run started on that mistaken assumption
(`32193725758`) was cancelled as a duplicate full rebuild.
