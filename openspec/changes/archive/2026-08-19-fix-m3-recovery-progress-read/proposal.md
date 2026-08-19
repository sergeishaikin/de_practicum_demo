## Authorisation

Authorised by the operator on 2026-08-19.

```text
AUTHORISED:      fix-m3-recovery-progress-read

NOT AUTHORISED:  add-static-typing-gate
                 every other NG backlog item
```

The authorisation was explicit that the `except ValueError` retry I had proposed
alongside the read fix is **not** included, and requires new evidence before it
could be. That correction is adopted; see design.md.

## Why

`H1 clean reproducible stack` failed on `d22b4c1`:

```text
FAILED tests/integration/test_m3_b2_recovery.py::test_m3_b2_projection_and_crash_recovery
json.decoder.JSONDecodeError: Extra data: line 1 column 515 (char 514)
```

That is the signature established and fixed earlier the same day in
`diagnose-medallion-progress-read-corruption`: `open_input_file` is random
access, so it sizes its read from a HEAD taken at open and applies that length
to a body fetched later. The medallion progress object is overwritten in place
and **shrinks** when work completes — a `work` entry holding full object paths is
replaced by a compact `completed` one — so a read issued across that overwrite is
sized by the larger predecessor and served the smaller successor. PyArrow returns
the whole over-sized buffer, and the tail is memory that was never written.

That fix made both **production** readers sequential. A third reader was missed:
the M3 integration test's own poller, `wait_for_completed`, still called
`open_input_file`. It polls once a second across exactly the overwrite that
shrinks the object, so it is if anything better placed to hit the race than the
production code was.

The failure is intermittent, and that is established rather than assumed. Three
consecutive CI runs of byte-identical test and runtime code:

| SHA | H1 clean stack | Difference from predecessor |
|---|---|---|
| `7d9977d` | pass | — |
| `d22b4c1` | **fail** | `openspec/` and `docs/` only |
| `2ec7376` | pass | `openspec/` and `docs/` only |

Nothing executable changed between them, so the failure is a race in the reader,
not a regression from those commits.

## What Changes

- `tests/integration/test_m3_b2_recovery.py` — `wait_for_completed` reads with
  `open_input_stream` instead of `open_input_file`. One call. The retry clause is
  **unchanged**, and a docstring records why each half is the way it is.
- `tests/integration/test_progress_read_under_shrink.py` — three added tests, in
  the file that already owns this defect class:
  - the M3 poller reads sequentially (source assertion, mirroring the existing
    writer test);
  - the M3 poller's retry loop does not absorb a decode failure;
  - a malformed object still raises through the sequential reader.

Test-only. No production code, no runtime semantics, no state contract.

**Scope fence, checkable rather than descriptive.**

Allowed: `tests/integration/test_m3_b2_recovery.py`,
`tests/integration/test_progress_read_under_shrink.py`, and this change's own
artifacts.

Forbidden, and checkable as such:

- `git diff --exit-code iceberg/` SHALL be clean. No production reader, business
  rule, Kafka/Iceberg state contract or medallion semantic is touched.
- The poll interval is not changed, the 90-second deadline is not inflated, and
  no backoff or retry mechanism is added. A timing change would mask the race
  rather than remove it, and would make any subsequent green run unattributable.
- `JSONDecodeError`, `UnicodeDecodeError`, `ValueError` and bare `Exception` are
  **not** added to the retry clause. A test now fails if they are.
- No assertion is weakened or deleted; no test is skipped or xfailed.
- `tests/support/progress_read_diagnostics.py` is not touched. Its
  `open_input_file` call is deliberate — reproducing the random-access read *is*
  its purpose.
- `openspec/backlog/**` is not touched and no NG item is started.
- Work stops when this change is archived.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The rule this change obeys — a fail-closed contract is not weakened to make
a check pass — is already carried by `verification-contract` and
`engineering-governance`. Adding a requirement restating it for one test helper
would produce a second, driftable statement of an existing rule.

## Impact

- `tests/integration/test_m3_b2_recovery.py` — one call, plus a docstring.
- `tests/integration/test_progress_read_under_shrink.py` — three added tests.
- `iceberg/`, `dags/`, `dbt/`, Compose, dependencies, CI, `.planning/`,
  `openspec/backlog/` — deliberately untouched.
