---
phase: 04-medallion-telemetry-and-redundant-work-elimination
plan: 07
subsystem: documentation
tags: [documentation, observability, requirements, traceability, contract]

requires:
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 02
    provides: cycle_id, phase and the three snapshot id columns; classify_metric_row
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 03
    provides: the phase records a cycle actually emits
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 05
    provides: the Gold provenance stamp and the rebuild skip being documented
  - phase: 04-medallion-telemetry-and-redundant-work-elimination
    plan: 06
    provides: the durable shadow certificate and the fast path being documented
provides:
  - corrected observability contract in README.md, CLAUDE.md, docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, docs/TESTING.md and docs/observability/O1-runtime-observability.md
  - the MTL-02 interpretation rule in prose, with its provenance stated
  - the cycle-only Prometheus contract recorded as deliberate
  - Phase 4 requirement IDs registered in .planning/REQUIREMENTS.md with honest statuses
affects: [04-08, 04-09, 04-10]

tech-stack:
  added: []
  patterns:
    - "Document a classification rule by pointing at its executable form, so prose and code cannot drift apart silently"
    - "State the provenance of a documented rule: which branches came from recorded data and which were derived by reading code"
    - "Record an identifier collision in the file that exists to prevent it, not only in the phase artifact that noticed it"
---

# Phase 4 Plan 07: Documentation Contract Correction and Requirement Registration Summary

## What the change actually is

Documentation only. No file under `iceberg/`, `dags/`, `spark/`, `tests/`,
`observability/` or either compose file was touched, and the scope fence was
checked with `git diff --exit-code` rather than assumed.

Two things were wrong before this plan. Five contract documents stated that a
medallion cycle writes one metrics row, which stopped being true in 04-03 — a
cycle writes one row per executed phase plus a `cycle` envelope row — and two
sample queries therefore double-counted every cycle two to four times. And
`.planning/REQUIREMENTS.md` mapped fifteen requirements while claiming
"Unmapped: 0", with none of Phase 4's identifiers present.

## What was built

**Task 1 — the observability contract.** `README.md`, `CLAUDE.md`,
`docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/TESTING.md` and
`docs/observability/O1-runtime-observability.md` now describe the cycle as
shipped: the writer contributes one row per batch, the medallion contributes
`b2`, `shadow`, `gold` and `cycle` rows sharing a `cycle_id`, with the `cycle`
row written last as the envelope. Both sample queries filter
`phase = 'cycle' or phase is null` and say why. `README.md`'s column table gains
`cycle_id`, `phase`, the three snapshot ids, `shadow_skipped` and `gold_skipped`.

The honest wart is written down: phase durations are mutually non-overlapping
but sum to *at most* the cycle duration, because the incremental writer's
state-load preamble runs before `run_b2` starts its timer and is attributed to
no phase.

MTL-02 gains its prose form — the status-qualified table for `cycle_id IS NULL`
rows, using the labels `classify_metric_row` actually returns, with `failed`
documented as `nested` rather than `b2` and the reason stated: the row may come
from the incremental write or from an aborted legacy cycle under
`QUALITY_FAIL_ON_VIOLATIONS=1`, and what both origins share is that no outer
record exists. The naive `gold_duration_ms = 0` rule is called out as
misclassifying `shadow_failed`, the safety-critical row.

The provenance statement appears in both `README.md` and the O1 document: the
two `success` branches are grounded in recorded data, the `shadow_failed` and
`failed` branches were **derived by reading the emission sites, not observed** —
every one of the ten rows in `artifacts/b2-rollout/06-o1-window.json` has
`status: success`.

O1 records the Prometheus contract as deliberate: only the `cycle` phase reaches
the collectors, because these gauges are labelled by `source` alone and a nested
record would let the outer record reset it to zero — the effect that weakened
`LakehouseUnresolvedWork`. The metric list and every label set are unchanged, so
no Grafana target or alert rule needed rewriting. The ownership table gains the
Gold provenance stamp and the shadow certificate.

Both skips are documented with their fail-safe direction in `README.md` and
`docs/ARCHITECTURE.md`, including that a Trino maintenance rewrite of Gold
deliberately costs one extra rebuild, and that a certificate found stale after
the Bronze pin was already skipped fails the cycle closed before Gold. Row
growth is restated: roughly two to four rows per cycle where there were two, so
about 970 rows/day scales accordingly; retention was not decided in this phase.

**Task 2 — requirement registration.** `MTL-01`, `MTL-02`, `SHD-01` and
`GLD-01` are registered Complete; `POL-01`, `BENCH-01` and `PRF-01` Pending. The
traceability table gains one row per requirement, mapped to Phase 4, and the
coverage counts are recomputed.

## Deviations from plan

**One, in Task 1's acceptance grep.** Four of its patterns are substrings of
sentences that are true of the *writer*, which does write one row per batch — so
the criterion as written could only be satisfied by making accurate prose worse.
Those sentences now say "a single row" instead. The check still catches a
resurrected per-cycle claim, and no claim was weakened to pass it.

**Source of truth for SHD-01.** The certificate fast path is documented as the
behaviour after `71d20be`, not as 04-06's original wording: pre-writer Bronze and
Silver metadata identity, post-writer revalidation of that pair, and a stale
certificate under the cutover fast path failing closed before Gold. The disputed
sentence in `04-06-PLAN.md` carries a dated correction and was deliberately not
carried into these documents as contract.

## Status decisions, determined rather than assumed

| Requirement | Status | How it was determined |
|---|---|---|
| `MTL-01` | Complete | 04-02 and 04-03 landed; `cycle_id`, `phase` and the snapshot ids exist in `METRICS_DDL` and are emitted |
| `MTL-02` | Complete | `classify_metric_row` landed in 04-02; the prose rule is this plan's Task 1 |
| `SHD-01` | Complete | 04-06 plus the stabilization at `71d20be`; live proof in ci-m5-gates (8 BDD scenarios, cross-restart certificate) |
| `GLD-01` | Complete | 04-05; live proof in ci-m5-gates |
| `POL-01` | **Pending** | `docs/adr/0002-steady-state-shadow-policy.md` does not exist on disk. The plan makes this the deciding test, and it was checked with `ls`, not inferred from 04-08 being planned |
| `BENCH-01` | Pending | 04-09 has not run; may still end as `NOT MEASURED` on an operator refusal |
| `PRF-01` | Pending | 04-10 has not run |

## Findings recorded rather than fixed

**Two identifier collisions are now visible in `REQUIREMENTS.md`.** `TEL-01` was
not reused — it is an already-Complete Phase-1 requirement and overloading it
would give one identifier two statuses, which is precisely what the file exists
to prevent. Separately, Phase 4's `GLD-01` is **not** the historical `GOLD-01`:
one letter apart, both about Gold, different requirements. That distinction was
not previously written anywhere a reader of the table would find it.

**"Unmapped: 0" was already false before Phase 4.** Phase 3's identifiers
(`R1`, `R1c`, `R2`, `R2b`, `R2c`, `R2d`, `R3`, `R6`, `R7`) were never added to
the file. No Phase 3 entries were invented here; the count now reads
`Unmapped: 9` with a note pointing at `.planning/ROADMAP.md`, so the gap is
visible instead of perpetuated. Closing it is its own task.

**Two repository-wide gates remain red, and neither is Phase 4 evidence.** The
`H1 clean reproducible stack` workflow and the ordinary `CI` warehouse job fail
for unrelated reasons. Phase 4's SHD/GLD evidence is green in ci-m5-gates; these
two are separate, known and out of this plan's scope, and were not investigated
or touched here.

## Verification performed

| Command | Result |
|---|---|
| `uv run --locked pytest -q tests/test_observability.py tests/test_h1_runtime.py` (Task 1 verify) | 52 passed |
| Task 2 registration check from the plan | `requirements registered` |
| `uv run --locked ruff check .` | All checks passed |
| `uv run --locked black --check .` | 71 files unchanged |
| `uv run --locked pytest -q` | 392 passed, 63 deselected |
| `git diff --exit-code -- iceberg/ dags/ spark/ tests/ observability/ docker-compose.yml docker-compose.extended.yml` | clean |
| Acceptance greps for the stale claims, the `phase = 'cycle'` filter, the seven new columns, `classify_metric_row`, the cycle-only Prometheus statement | all pass |

No live stack was started; nothing stateful was created, contacted or mutated.
A documentation-only change does not require the live layer, and `AGENTS.md`
scopes the Python completion gate to non-documentation changes — it was run
anyway, since the repository test suite reads several of these documents.

## Commits

| Commit | Content |
|---|---|
| `5bbe65b` | Task 1 — the observability contract across six documents |
| `55ac85a` | Task 2 — Phase 4 requirement registration |

## Interface for downstream plans

`04-08` may now assume the observability contract in the documents matches the
code, that `POL-01` is registered Pending and that ratifying ADR-0002 is what
flips it, and that `BENCH-01` is registered in a form that admits a
`NOT MEASURED` outcome.

## Self-Check: PASSED

Both task commits are present in `git log`; every file this plan claims to have
changed is in their diffs and no file outside the authorised set is.
