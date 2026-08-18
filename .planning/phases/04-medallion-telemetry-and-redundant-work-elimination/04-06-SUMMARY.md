---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 06
subsystem: medallion
tags: [medallion, shadow-validation, certificate, minio, fast-path, iceberg, cutover]

requires:
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 02
    provides: the shadow_skipped column and the Metrics.record keyword that carries it
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 03
    provides: _read_persisted_silver returning (rows, snapshot_id) and the shadow phase record
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 04
    provides: CYCLE_COMPLETE_MARKER, CycleOutcome, CycleWatcher, parse_cycle_marker, gold_snapshot_count
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 05
    provides: _gold_provenance, the Gold rebuild skip, and gold=skipped in the cycle marker
provides:
  - MEDALLION_SHADOW_RECEIPT_PATH, SHADOW_RECEIPT_VERSION, SHADOW_CONTRACT_VERSION
  - _shadow_receipt_path(), load_shadow_receipt(fs), save_shadow_receipt(fs, receipt)
  - shadow_receipt_is_valid(receipt, *, bronze_snapshot_id, silver_snapshot_id, runtime_identity, projection_identity)
  - _shadow_projection_identity() and _runtime_identity(selected_mode)
  - _bronze_snapshot_id(catalog) and _silver_snapshot_id(catalog), both metadata-only
  - the receipt-gated fast path in _run_m4 skipping the Bronze pin, the legacy rebuild and the comparison
  - shadow_skipped on the shadow and cycle metric records; shadow=skipped reachable in the cycle marker
  - run_deployment(..., require_gold=, require_shadow=) returning the announced cycle marker
  - a cross-restart certification scenario in tests/features/gold_cutover.feature
affects: [04-07 documentation contract, 04-08 measurement, 04-09, 04-10]

tech-stack:
  added: []
  patterns:
    - "Certify a correctness gate's conclusion with a durable receipt whose identity covers every input that conclusion depends on; skip only while all of them still match"
    - "Split a durable artifact's read and write contracts when they are opposite: the read fails toward doing the work, the write is best-effort"
    - "Compose an identity from a digest that moves on its own plus a hand-bumped constant, so the likely change invalidates automatically and the unlikely one is still expressible"
    - "Decide a skip from table metadata only, so declining to scan never costs a scan"
    - "Touch the object store only once every identity is known, which keeps in-memory doubles network-free by construction"

key-files:
  created: []
  modified:
    - iceberg/medallion/iceberg_medallion.py
    - tests/test_m4_gold.py
    - tests/features/gold_cutover.feature
    - tests/features/test_gold_cutover.py
    - tests/support/medallion_harness.py
    - docker-compose.extended.yml
    - .env.example
    - docs/CONFIGURATION.md

key-decisions:
  - "The certificate is a MinIO object, not the PostgreSQL table 04-RESEARCH 3d recommended. ci-m5-gates.yml starts only minio and iceberg-rest and runs the medallion with METRICS_ENABLED=0, so a PostgreSQL receipt would make the fast path unreachable in the only integration proof this repository has. The Architectural Responsibility Map row already names MinIO; the implementation matches it and the map was not edited."
  - "The gate's Silver snapshot id is read before the incremental writer by a new _silver_snapshot_id, not taken from _read_persisted_silver's post-writer return as the plan's action text says. Taking the plan literally would have violated one of its own locked constraints — see Deviations."
  - "_read_persisted_silver stays unconditional, a recorded decision against research Open Question 4, with the reasoning written into the code as a comment."
  - "The pin and the legacy rebuild are skipped only when the receipt is valid AND GOLD_SOURCE is not legacy. Under the shadow stage the legacy projection is Gold's input, so skipping it would break the cycle rather than optimise it."
  - "The fast-path gate is evaluated only when SHADOW_COMPARE is enabled. With validation off there is no comparison to skip and the pin is required work, so an unconditional gate would be a pointless object-store read on every cycle."
  - "No new status literal. A skipped comparison is expressed as shadow_skipped on the metric rows plus shadow=skipped in the cycle marker, exactly as 04-05 expressed a skipped Gold."
  - "The receipt written after a passing comparison carries the pinned Bronze snapshot id and the post-writer Silver snapshot id — the two the comparison actually validated — not the ids the gate read."
  - "MEDALLION_COMPLETION_LEDGER_PREFIX was declared in compose, .env.example and docs/CONFIGURATION.md alongside the new variable, closing the pre-existing gap research flagged."

patterns-established:
  - "Asymmetric durable-state contracts documented at the point of asymmetry: load_shadow_receipt never raises while its neighbour load_completion_ledger does, and the docstring says why, so the difference reads as a decision rather than an inconsistency."
  - "A live-harness wait that carries its own assertion: run_deployment can be told which decision to wait for, so a deployment that never makes it fails as a timeout naming the expectation."

requirements-completed: [SHD-01, MTL-01, REGR-1, REGR-2, REGR-3, REGR-4]

duration: unrecorded
completed: 2026-08-18
---

# Phase 4 Plan 06: The Durable Shadow Certificate and the Receipt-Gated Fast Path Summary

**A passing shadow comparison now leaves a durable MinIO certificate naming both snapshots, the runtime and the projection contract it validated, and a later cycle skips the Bronze scan, the legacy rebuild and the comparison only while all four still match — every other outcome, including every way of failing to read the certificate, runs the full comparison.**

## What the change actually is

At the measured baseline the pinned Bronze scan, the legacy Silver rebuild and the business-state
comparison were 21–45 s of a 26–50 s cycle, and four of the five recorded cycles did no work at
all. Those four re-derived from scratch a conclusion an identical earlier cycle had already
reached.

The comparison itself is untouched and is not weakened. What is elided is a comparison whose
inputs are provably the same as the inputs of a comparison that already passed. "Provably the
same" is four identities, all carried on the certificate: the Bronze snapshot id, the persisted
Silver snapshot id, the effective runtime (mode + `GOLD_SOURCE` + `SHADOW_COMPARE`), and the
projection contract (`SHADOW_CONTRACT_VERSION` plus a `sha256` digest of the business and excluded
column tuples). Any one of them moving forces revalidation.

Bronze and Silver are both required because they move independently — Silver can advance through
B2 recovery with Bronze unchanged, which is why Bronze identity alone would have been unsafe.

## What was built

**Task 1 — `7053ce4`** (`iceberg/medallion/iceberg_medallion.py`, `tests/test_m4_gold.py`,
`docker-compose.extended.yml`, `.env.example`, `docs/CONFIGURATION.md`).

`MEDALLION_SHADOW_RECEIPT_PATH` (default `streaming/medallion/shadow-certification.json`) and
`SHADOW_RECEIPT_VERSION = 1` sit with the other durable-state constants; `_shadow_receipt_path()`
sits beside `_progress_path()` and is built with the existing `_storage_path` helper.

`load_shadow_receipt(fs)` returns `None` — never raises — for an absent object, an unreadable one,
invalid JSON, a payload that is not an object, and a receipt of any other version. Its docstring
states the asymmetry with the neighbouring `load_completion_ledger`, which *does* raise, and why:
an ambiguous completion receipt is two contradictory claims about one load id, a correctness fork
worth stopping the service for, whereas an unusable shadow certificate only means "not certified".

`save_shadow_receipt(fs, receipt)` swallows every exception in the style of `Metrics.record`, and
only on the write side, because a certificate that never lands costs exactly one redundant
comparison. Failures log the cycle id and the exception type; no row payload is ever logged.

`_shadow_projection_identity()` is `contract={SHADOW_CONTRACT_VERSION};columns={sha256}` over a
canonical rendering of `("business",) + SHADOW_BUSINESS_COLUMNS + ("excluded",) +
SHADOW_EXCLUDED_COLUMNS`. The separator token means moving a column between the two tuples is a
different string rather than the same multiset. `SHADOW_CONTRACT_VERSION` carries the Pitfall 7
comment the plan requires: a hand-maintained constant alone would be a silent-staleness hazard,
which is why the digest is there.

`_runtime_identity(selected_mode)` is built from the **effective** mode plus the module
`GOLD_SOURCE` and `SHADOW_COMPARE_ENABLED`, so a monkeypatched rollout stage produces a different
identity and a certificate produced in `shadow` cannot authorise a skip in `cutover`.

`shadow_receipt_is_valid(...)` is pure and returns `True` only when the stored result is `equal`
and all four identities match. It returns `False` for `None`, for a non-dict, for a non-`equal`
result, for any identity mismatch, and — the T-04-22 rule — whenever either current snapshot id is
`None`, so `None == None` can never certify an empty or unknown lake.

Both `MEDALLION_SHADOW_RECEIPT_PATH` and the pre-existing, previously undeclared
`MEDALLION_COMPLETION_LEDGER_PREFIX` are now declared in the `iceberg-medallion` service
environment, in `.env.example`, and in `docs/CONFIGURATION.md`. Two declarations, not one.

**Task 2 — `bd0b071`** (`iceberg/medallion/iceberg_medallion.py`, `tests/test_m4_gold.py`).

`_bronze_snapshot_id(catalog)` and `_silver_snapshot_id(catalog)` load the table and read
`_snapshot_id`, returning `None` on `NoSuchTableError`. Metadata only — deciding not to scan Bronze
must not itself cost a Bronze scan.

`_run_m4` computes `needs_legacy_projection = (GOLD_SOURCE == "legacy")` and, when
`SHADOW_COMPARE` is on and **both** ids are non-`None`, reads the certificate and evaluates
`shadow_receipt_is_valid`. The filesystem is materialised lazily at the point of use
(`fs if fs is not None else get_fs()`), never at the top of the function: the only two `get_fs()`
occurrences inside `_run_m4` are the receipt read and the receipt write.

The skip is applied only where the work is validation work:

| Rollout state | Bronze pin | Legacy rebuild | Comparison |
|---|---|---|---|
| `cutover`, receipt valid | skipped | skipped | skipped |
| `shadow`, receipt valid | **runs** (Gold's input) | **runs** | skipped |
| any state, receipt invalid or absent | runs | runs | runs |

`_read_persisted_silver` stays unconditional, with the reasoning against research Open Question 4
written into the code: it feeds Gold at cutover, coupling it to the Gold skip would entangle
SHD-01 and GLD-01 into one conditional, and the `shadow` phase duration now measures it directly,
so a later decision to elide it can be made on evidence.

After a comparison that returns `equal`, the receipt is written best-effort with the pinned Bronze
snapshot id and the post-writer Silver snapshot id — the two the comparison actually validated —
plus both identities, `result`, `compared_keys`, an ISO-8601 UTC `certified_at` and the `cycle_id`.
A mismatch raises before reaching it, so a failed comparison certifies nothing.

`shadow_comparisons` is now `int(shadow_compared)` rather than `int(SHADOW_COMPARE_ENABLED)`;
`shadow_skipped` rides the `shadow` and `cycle` records as its inverse (and is `False` when
validation is off, because there was never a comparison to skip); `CycleOutcome.shadow` becomes
`skipped` when the fast path fired. No new `status` literal was introduced. The `CycleOutcome`
docstring, which said `"skipped"` was not yet reachable, now says it is and what it means.

Thirty-two tests were added to `tests/test_m4_gold.py` across both tasks; the diff is **444
insertions and 0 deletions**, so every pre-existing contract in that file — including
`test_shadow_uses_bronze_boundary_pinned_before_b2_runs` (SHD-01f) — is byte-identical and green.

| Test | Behaviour bullet |
|---|---|
| `test_an_uncertified_cycle_compares_and_leaves_a_certificate` | no receipt → compare, then certify |
| `test_a_certified_cutover_cycle_does_no_validation_work` | cutover: pin, rebuild and comparison all skipped |
| `test_a_certified_shadow_cycle_still_builds_the_projection_gold_needs` | shadow: pin and rebuild still run |
| `test_a_moved_bronze_snapshot_forces_revalidation` | Bronze moved |
| `test_a_silver_snapshot_that_moved_independently_forces_revalidation` | B2 recovery case |
| `test_a_changed_identity_forces_revalidation[runtime_identity]` | runtime changed |
| `test_a_changed_identity_forces_revalidation[projection_identity]` | projection changed |
| `test_a_shadow_mismatch_still_fails_closed_and_certifies_nothing` | mismatch raises before Gold, no receipt |
| `test_unknown_snapshot_ids_never_touch_the_filesystem` | `None` ids → no read, no write, no `get_fs()` |
| `test_shadow_skipped_is_the_inverse_of_a_comparison_that_ran` | metrics and the marker |

The pre-existing Gold and metric contracts still pass unchanged because `setup_gold_run` leaves
both doubles snapshotless: no ids, so no certificate, so the full work. The new
`setup_certified_run` adds one snapshot to each, which is the only difference.

**Task 3 — `17317c1`** (`tests/features/gold_cutover.feature`,
`tests/features/test_gold_cutover.py`, `tests/support/medallion_harness.py`).

One scenario, *A certified comparison is not repeated by a later deployment*. The feature file
gained 16 lines and lost none, so the two existing scenarios are byte-identical. It walks the
`shadow` stage, then `cutover`, then a **second** `cutover` deployment — a different process —
over a lake whose Bronze and Silver did not move, and requires that second deployment to announce a
cycle with `shadow=skipped` and `gold=skipped`, with the daily metrics unchanged, the incremental
business state untouched (snapshot identity, not just rows), and the Gold snapshot count
unchanged.

Two independent observables on purpose: the deployment's own marker, and `gold_snapshot_count`
read from the catalog, which is true whatever the deployment says about itself. That is why
`gold_snapshot_count` was kept when `wait_for_new_gold_snapshot` was removed in 04-04.

`run_deployment` gained `require_gold` / `require_shadow`, passed through to
`CycleWatcher.wait_for_cycle_complete`, and now returns the announced marker, so the wait carries
the assertion. `start_medallion` sets `MEDALLION_SHADOW_RECEIPT_PATH` to a per-run path derived
from the per-run progress path by the new `shadow_receipt_path` helper, and `isolated_lake` deletes
it in cleanup, so the isolation guarantee holds and the canonical lake is never involved. The step
module's scope-boundary docstring gained an entry in the existing style, justifying the scenario as
the one thing in-memory doubles cannot show: cross-restart durability.

## Deviations from plan

**One, and it is load-bearing. Nothing was adjusted to make anything pass; no test, expected value
or assertion was edited.**

**The gate's Silver snapshot id is read before the incremental writer, not taken from
`_read_persisted_silver`'s return.** Task 2's action text says to take "the current
persisted-Silver snapshot id from the `_read_persisted_silver` return that 04-03 already
provides". That value is produced *after* `run_b2`. The gate has to be decided *before* `run_b2`,
because the thing it gates — `_pin_bronze_boundary` — must precede the writer.

Implementing the sentence literally has only two forms and both contradict a locked constraint of
this same plan:

1. move the Bronze pin after the writer, which breaks *"a comparison that does run still uses the
   Bronze boundary pinned before the incremental writer"* and makes shadow evidence race with
   ingestion; or
2. move `_read_persisted_silver` before the writer, which leaves Gold built from a pre-writer
   Silver read — a change to the Gold semantics 04-05 delivered, which this execution was told not
   to touch.

So `_silver_snapshot_id(catalog)` reads the id early, from table metadata only, and
`_read_persisted_silver` stays exactly where it was and still supplies the id that Gold
provenance, the metric rows and the written receipt record. The plan's other two statements about
that call — that it stays unconditional, and that the receipt certifies what the comparison
validated — are honoured exactly.

Why the early read is safe, stated so it can be checked rather than trusted: `run_b2` moves Silver
only when it finds committed outbox work; committed outbox work implies a Bronze append; a Bronze
append moves the Bronze snapshot id, which invalidates the certificate on its own. A cycle that
crashes or raises mid-writer never reaches the receipt write, so it certifies nothing. The
reasoning is recorded in `_silver_snapshot_id`'s docstring, not only here.

`_silver_snapshot_id` is therefore one symbol more than the plan's artifact table lists. It is
additive and private; nothing in the plan is contradicted by its existence.

**Not a deviation, recorded for completeness:** the plan's Task 1 read list says
`docker-compose.extended.yml` lines 319–369 contain the medallion service and that
`MEDALLION_COMPLETION_LEDGER_PREFIX` is absent there — both were true, and both declarations were
added as instructed.

## Scope — what was deliberately not done

- 04-07, 04-08, 04-09 and 04-10 were not started and not prepared for.
- Gold semantics from 04-05 are untouched: `_write_gold`, `_gold_provenance` and
  `GOLD_SOURCE_SILVER_SNAPSHOT_KEY` are unchanged, and the plan's key is not reused.
- 04-04's marker contract is untouched apart from `shadow` gaining a value the docstring already
  reserved. `MARKER_FIELDS`, `parse_cycle_marker` and `CycleWatcher` are unchanged.
- `compare_business_state` is byte-identical. Nothing about what a comparison decides changed.
- No PostgreSQL storage for the certificate. No new orchestration or runtime component.
- `iceberg/common/cutover.py` and `iceberg/b2_spike.py` are byte-identical
  (`git diff --exit-code` clean).
- `tests/features/shadow_cutover.feature` and its steps are untouched; their
  `shadow_comparisons == 1` assertions still hold at their existing values, because those doubles
  have no snapshots and therefore can never be certified.
- The failing H1 workflow and the unrelated warehouse CI failure were not touched.
- **No Docker service was started.** No container, volume, checkpoint, Kafka record, MinIO object
  or Iceberg table was created, contacted or mutated. `docker compose config --quiet` was run — it
  validates configuration and starts nothing.

## Verification performed

Every command below was executed in this session and these are its real figures.

| Check | Result |
|---|---|
| `uv run --locked pytest -q tests/test_m4_gold.py tests/test_b2_medallion.py` (task 1 verify) | **62 passed** |
| `grep -n "MEDALLION_SHADOW_RECEIPT_PATH" docker-compose.extended.yml .env.example docs/CONFIGURATION.md` | one hit in each of the three |
| `grep -n "MEDALLION_COMPLETION_LEDGER_PREFIX" docker-compose.extended.yml .env.example docs/CONFIGURATION.md` | one hit in each of the three |
| `uv run --locked pytest -q tests/test_m4_gold.py tests/test_b2_medallion.py tests/features tests/test_m5_fitness_functions.py` (task 2 verify) | **126 passed, 23 deselected** |
| `uv run --locked pytest -q tests/test_m5_fitness_functions.py -m architecture` (REGR-4) | **12 passed** |
| `grep -n "get_fs()" iceberg/medallion/iceberg_medallion.py` | 4 hits: the definition (158), the pre-existing `run_b2` default (538), and inside `_run_m4` only the receipt read (1500) and the receipt write (1579) |
| `git diff --numstat tests/test_m4_gold.py` across both tasks | **444 insertions, 0 deletions**; 32 new tests (30 → 62 collected) |
| `git diff --numstat tests/features/gold_cutover.feature` | **16 insertions, 0 deletions** — the existing two scenarios byte-identical |
| `git diff --exit-code iceberg/common/cutover.py iceberg/b2_spike.py` | clean |
| `uv run --locked pytest -q --collect-only tests/features/test_gold_cutover.py -m integration` (task 3 verify) | **3 tests collected**, including `test_a_certified_comparison_is_not_repeated_by_a_later_deployment` |
| `uv run --locked ruff check .` | All checks passed! |
| `uv run --locked black --check .` | 71 files would be left unchanged |
| `uv run --locked pytest` | **389 passed, 63 deselected** (baseline at 85b95aa: 357) |
| `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` | pass, **94.25%** total (was 94.12% after 04-05); `iceberg_medallion.py` **92%** |
| `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet` | **exit 0** |
| `uv run --locked pytest -q tests/test_h1_runtime.py` (`.env.example` is touched) | **47 passed** |
| `uv run --locked python scripts/validate_runtime_config.py --env-file .env.example` | exit 1 — **pre-existing and expected**: it reports only placeholder secrets (`POSTGRES_PASSWORD`, `MINIO_ROOT_PASSWORD`, the three Airflow secrets, `SUPERSET_SECRET_KEY`), which is what `.env.example` is for. It reports nothing about either new variable. `ci-pr` runs the compose check above, not this script, against `.env.example`. |
| lock/compose freshness (`ci-pr` stale-lock check) | no dependency input was touched; `uv.lock` and the nine generated lock/export files are unmodified in `git status` |

### The `-m bdd` marker trap, reported both ways

The plan's task-2 acceptance criterion names `uv run --locked pytest -q tests/features -m bdd`. It
was run verbatim: **23 failed, 41 passed, 5 errors in 100.20 s**.

That command overrides `pytest.ini`'s `addopts = -m "not integration and not e2e and not airflow"`,
so it selects the live-stack and Airflow scenarios as well. Collection proves the split
statically: of the 65 tests it collects, `-m "bdd and not integration and not airflow and not e2e"`
selects **41** and `-m "bdd and (integration or airflow or e2e)"` selects **24**. The 41 that can
run without services are exactly the 41 that passed; every failure and error lies inside the 24
that cannot, in files this plan did not modify (`test_iceberg_writer.py`,
`test_writer_crash_recovery.py`, `test_airflow_workflow_behavior.py`, and the integration
scenarios of `test_gold_cutover.py`). They are connection failures against an absent local catalog
and an absent Airflow, not breakage introduced here, and they are not silenced.

The correctly filtered substitute was run and is green:
`uv run --locked pytest -q tests/features -m "bdd and not integration and not airflow and not e2e"`
→ **41 passed, 23 deselected**. `uv run --locked pytest -q tests/features` (default filter) →
**41 passed** as part of the task-2 verify line above.

## Not verified — the live layer was **not executed here**

Specifically **not** run, because this execution was not authorised to start or contact any
service:

- `uv run --locked pytest -q tests/features -m "bdd and integration"` — 8 tests collected,
  including the new certification scenario.
- `uv run --locked pytest -q -m integration tests/integration/test_m3_b2_recovery.py tests/integration/test_m4_gold_cutover.py` — 2 tests collected.
- `ci-m5-gates.yml`, `ci-integration.yml`, `ci-nightly.yml`.

Both live commands were `--collect-only`'d, which contacts nothing, and both collect cleanly.
`ci-m5-gates.yml` triggers on `iceberg/**` and `tests/test_*.py`, both of which this change
touches, so it will run them on the PR.

**What that leaves unproven, stated plainly:**

1. **SHD-01h — that the certificate actually survives a process boundary.** The unit layer proves
   what a certificate decides, using `FakeFS`, which models the `S3FileSystem` slice in use; it
   cannot prove that a real `S3FileSystem` writes an object a *different process* can read back
   through MinIO. That is exactly what the new scenario exists for, and it did not run here.
2. **That a real `pyarrow.fs.S3FileSystem` raises `FileNotFoundError`/`OSError` (not something
   else) for an absent receipt object.** `load_shadow_receipt` catches `FileNotFoundError`
   explicitly and everything else broadly, so an unexpected exception type still degrades to "not
   certified" rather than breaking the cycle — but the first cycle of a fresh deployment reading a
   receipt that does not exist yet is only exercised for real in the live gate. The pre-existing
   `load_progress` catches the same pair against the same store, which is the precedent this
   follows.
3. **That the fast path measurably removes the 21–45 s.** Nothing here measures a live cycle;
   04-08 is the measurement plan.

### One observation for a later plan, not fixed here

`tests/integration/test_m4_gold_cutover.py` has its own `start_medallion` and does **not** set
`MEDALLION_SHADOW_RECEIPT_PATH`, so under `ci-m5-gates` it will read and write the *canonical*
default path in the shared bucket rather than a per-run one. That file is not in this plan's
authorised file list, so it was left alone. The consequence is bounded and fail-safe: a receipt
written by one namespace names that namespace's snapshot ids, which cannot match another's, so a
stale certificate can only cause a redundant comparison, never a false skip. It is untidiness in
shared test state, not a correctness hole.

`tests/integration/test_m3_b2_recovery.py` is unaffected either way — it never sets
`SHADOW_COMPARE`, so the gate is not evaluated and the object store is not touched by it.

## Commits

- `7053ce4` — feat(04-06): certify a passing shadow comparison durably
- `bd0b071` — feat(04-06): skip validation work a certificate already covers
- `17317c1` — test(04-06): prove the certificate outlives the process that wrote it

## Interface for downstream plans

04-07 (documentation) should document `MEDALLION_SHADOW_RECEIPT_PATH` as operator-visible: the
certificate is not SQL-queryable by design, so the *decision* it drives is what operators read —
`shadow_skipped` and `shadow_comparisons` on the metric rows, and `shadow=skipped` in the cycle
marker. It should also document the invalidation rules, because "why did validation suddenly start
running every cycle again" has exactly four answers.

04-08 (measurement) can compare the `shadow` phase `duration_ms` on skipped versus compared
cycles; the `shadow` record is still emitted on a skip so that number exists, and
`_read_persisted_silver` is deliberately still inside that segment, so the residual cost of a
skipped cycle is directly measurable rather than inferred.

Later plans must not relax `shadow_receipt_is_valid`: all four identities plus `result == "equal"`
are the whole security property, and both current snapshot ids must be non-`None` before the object
store is touched at all.

## Self-Check: PASSED

All eight modified files and this SUMMARY exist on disk; all three task commits (`7053ce4`,
`bd0b071`, `17317c1`) are present in `git log`.
