# Evidence — diagnose-medallion-progress-read-corruption

## The two observations

| | run 1 | run 2 |
|---|---|---|
| SHA | `a576c31` | `a576c31` (rerun) |
| step | `M5 PR blocking live gates` | `PR blocking BDD specifications` |
| test | `test_m4_persisted_silver_gold_shadow_and_rollback` | `test_a_certified_comparison_is_not_repeated_by_a_later_deployment` |
| error | `JSONDecodeError: Extra data: line 1 column 238 (char 237)` | `UnicodeDecodeError: can't decode byte 0xc0 in position 240` |
| tail | ASCII, resembling a `PATH` value | binary |

Two different tests, the same read shape, garbage at the same offset region,
**different** garbage each time. A flaky timeout does not produce that.

## Control experiment

Run exactly once, as instructed, before any other work.

| SHA | M5 observations | result |
|---|---|---|
| `7c4c7c7` | 2 | green, green |
| `a576c31` | 2 | **red, red** |
| `65c0f33` | 2 | green, green |
| `086dd1e` | 1 | green |

`a576c31` is the only red SHA and it is red 2/2. Its diff touches
`artifacts/`, `docs/`, `openspec/` and `scripts/` only. The M5 gates run
`tests/integration/test_m3_b2_recovery.py`, `tests/integration/test_m4_gold_cutover.py`
and `tests/features -m "bdd and integration"`; `pytest.ini` sets
`testpaths = tests`, so `scripts/` is never collected, and nothing in that diff
is imported by anything that is. The stack images are pinned through `.env`, so
the environment is identical across all seven runs.

**Correlation observed, causation not established** — that was the honest reading
at the time, and it held. The root cause below is a race between a read and a
shrinking overwrite, so which SHA it lands on carries no information: `a576c31`
being red twice was the race landing twice, not `a576c31` causing anything. The
control experiment earned its cost by keeping the diagnosis off that dead end.

## What was ruled out, by reading rather than by assuming

**Concurrent writers.** Each run owns `m4/{run_id}/progress.json`, and the first
medallion process is terminated and waited on before the second starts. One
writer, one reader polling once a second.

## What was established

**The progress document shrinks, and it shrinks exactly when the reader is
waiting.** `_reserve_b2_work` stores `source_paths` and `bronze_data_files` —
full object paths — under `work[load_id]`, then saves. Completion writes a
compact `completed` entry, pops the reserved one, prunes, then saves. Measured
on the unit fakes:

```text
progress sizes in bytes, in write order: [201, 123]
```

A 39 % shrink on a single work item. The M4 cutover test carries two work items
with longer paths, so a completed document around 237 bytes with a larger
reserved predecessor is the expected shape — and 237 is exactly where run 1
found a complete JSON document followed by bytes that were never written to it.

Pinned by `test_the_progress_document_shrinks_when_work_completes`, which fails
with the recorded sizes and states that it is stale rather than wrong if
reservation ever stops storing object paths.

A shrinking overwrite is the **precondition** for a read that spans two
versions. It is not proof that this is what happened.

## Root cause — established

Run `32270528355` on `271c2c3` reproduced it with the capture attached. The
report is decisive.

```text
file_info before the read     size 521      the pre-shrink document
size reported at open         521
first read                    521 bytes     236 valid + 285 of something else
second read                   size 236, parses, sha 99b40f74...
sequential read               236 bytes,     sha 99b40f74...  identical
```

**The stored object was never corrupt.** Two independent reads return the same
236 bytes with the same digest, and both parse.

The 285-byte tail is uninitialised process memory, not any document. The
captured bytes, as hex:

```text
db 7f 00 00        Linux x86-64 pointers (0x7fdb...), repeated
6d 69 6e 69 6f     the literal `minio`, a stray heap string
3a 3a 31           the literal `::1`
00 00 00 ...       long runs of zeros
```

Raw evidence: `first-read.bin`, `second-read.bin`, `sequential-read.bin` and
`report.json` in the `m5-read-corruption` artifact of run `32270528355`.

**Mechanism.** `open_input_file` is random access: it takes the object's length
from a HEAD at open, then applies that length to a body fetched afterwards. The
progress document shrinks — 521 to 236 here, 201 to 123 on the unit fakes — so a
read issued across the overwrite is sized by the larger predecessor and served
the smaller successor. PyArrow returns the whole over-sized buffer and the
unwritten tail is whatever the heap held.

**Class B, triggered by C.** The read returns extra bytes over an intact object;
the shrinking overwrite is what creates the size-body mismatch. D was already
weakened by the single-writer reading, and A is refuted outright by the second
and sequential reads agreeing.

This is also an information-disclosure defect, not only a correctness one:
process memory reached application data.

## Fix

Both production readers took the same random-access shape. Both now read
sequentially, which cannot be sized by a stale HEAD:

| site | before | after |
|---|---|---|
| `iceberg/medallion/iceberg_medallion.py` `_read_json` | `open_input_file` | `open_input_stream` |
| `iceberg/writer/iceberg_writer.py` `_read_spark_commit_log` | `open_input_file` | `open_input_stream` |

Minimal, local and reversible; the parsed document, the failure modes on a
genuinely bad object, and every data semantic are unchanged. The same evidence
that established the cause also demonstrates the remedy: in that report the
sequential read of the very same object returned the intact document.

Authorised under the standing rule for a proven root cause with a local,
semantics-preserving change, so it was made rather than queued.

## Regression contracts, proved by failing

- `test_progress_is_read_sequentially_not_by_advertised_size` — a recording
  double asserts `_read_json` uses the sequential API. **Demonstrated:** with the
  fix reverted it fails (`used == ['file']`); restored, it passes. No stack.
- `test_the_writer_commit_log_reader_is_sequential_too` — the same contract for
  the writer, asserted on its source.
- `tests/integration/test_progress_read_under_shrink.py` — against a real object
  store, forces the ordering the race hit by luck: observe the size while the
  object is large, replace it with a smaller one, then read. Asserts the
  medallion's reader returns one of the two documents exactly and never one
  followed by anything.
- `test_the_progress_document_shrinks_when_work_completes` — pins the
  precondition so the defect cannot silently return by a different route.

Two test doubles gained `open_input_stream`, in `tests/support/b2_fakes.py` and
`tests/test_writer.py`. Adding the fix without them turned 39 unit tests red,
which is the correct signal: a double that does not offer the API production
calls has stopped exercising the code that runs.

## Scope fence, verified

| Fence | Result |
|---|---|
| `iceberg/` changed only after the cause was proved | two readers, `open_input_file` to `open_input_stream`, nothing else |
| Fix is minimal, local, reversible, semantics-preserving | one call per site; parsed document and failure modes unchanged |
| No retry/sleep/backoff/truncation/weakened assertion | none added; the capture re-raises |
| `04-09` not started, no benchmark receipt emulated | holds |
| `04-10` disposition not revisited | holds |
| No storage-protocol, atomicity or progress-format change | none |

## Live proof, before and after

| | run | SHA | result |
|---|---|---|---|
| before | `32264514538` | `a576c31` | M5 red, both steps, corruption in two tests |
| before | `32270528355` | `271c2c3` | M5 red, corruption captured byte for byte |
| **after** | **`32271503301`** | **`0811e60`** | **M5 green** |
| after | `32271503597` | `0811e60` | CI green |
| after | `32271503425` | `0811e60` | S1 green |
| after | `32271503302` | `0811e60` | H1 green — no contradicting evidence |

The defect has a live before-and-after on the same gate. H1 was checked because
the fix touches the writer as well as the medallion, and a clean-stack run is
where a writer regression would surface.

## What this change deliberately did not do

- **No security workstream.** The uninitialised-memory tail is severity evidence
  for a defect that is now fixed, not a separate finding. Sequential reads remove
  the exposure and the regression contracts hold it removed.
- **No fix for the double `collapse_delta`.** It stays a follow-up observation
  recorded in the 04-10 profile. Its 11.8 % synthetic share at 10^6 rows is not
  grounds for an optimisation, and none was made.
- **`04-09` not started.** No benchmark receipt created or emulated, no canonical
  warehouse state touched.

