# Phase 4: Medallion Telemetry and Redundant Work Elimination - Context

**Gathered:** 2026-08-17
**Status:** Ready for planning
**Source:** PRD Express Path (operator brief) + pre-planning code verification

**Requirement IDs:** `MTL-01`, `MTL-02`, `SHD-01`, `GLD-01`, `POL-01`, `PRF-01`,
`BENCH-01`. The brief's `TEL-01` was renamed to `MTL-01` — `TEL-01` is already
taken by a **Complete** Phase-1 requirement (`REQUIREMENTS.md:30,76`) and reusing
it would corrupt the traceability table.

<domain>
## Phase Boundary

Make medallion execution telemetry trustworthy, then use that evidence to remove
redundant full-state work when Iceberg state has not changed.

**In scope:** metric identity and phase separation; a documented interpretation
rule for historical rows; a receipt-based shadow fast path; Gold source
provenance; a steady-state shadow policy decision; and Arrow/Python boundary
profiling *only if still measurable after the redundant work is gone*.

**Out of scope, explicitly:** Rust, or any new language or toolchain. No Rust
rewrite is justified by current evidence. The Bronze writer question is
*unmeasured*, not rejected — it may be reopened later on its own measurements,
and nothing in this phase should be shaped to make that easier or harder.

</domain>

<decisions>
## Implementation Decisions

All items are locked by the operator brief unless marked otherwise.

### P0 — Correct telemetry semantics

- Introduce a stable `cycle_id` identifying one outer medallion cycle.
- Distinguish `phase` explicitly: `b2`, `shadow`, `gold`, `cycle`.
- Phase durations must be **non-overlapping, or documented as inclusive** — one
  or the other, decided and stated, never left implicit.
- Record enough state to explain a cycle: `bronze_snapshot_id`,
  `silver_snapshot_id`, `gold_snapshot_id` where meaningful, work/files/keys
  processed, and the shadow comparison result.
- Dashboards and queries must not be able to double-count nested B2 time.
- Add tests proving one logical run produces one cycle record plus correctly
  associated phase records.

### P0 — The historical interpretation rule (CORRECTED before planning)

The brief proposed: `gold_duration_ms = 0` → nested B2; `> 0` → outer cycle.
**Verification against the code found that rule incomplete.** There are six
emission sites, not two:

| Site | Function | status | sets `gold_duration_ms`? |
|---|---|---|---|
| `iceberg_medallion.py:542` | `run_b2` | `failed` | no |
| `:602` | `run_b2` | `success` | no |
| `:979` | `_legacy_silver_cycle` | `failed` | no |
| `:1033` | `_run_legacy` | `success` | **yes** |
| `:1089` | `_run_m4` | `shadow_failed` | **no** |
| `:1109` | `_run_m4` | `success` | **yes** |

The corrected rule that must be documented and tested:

| `status` | `gold_duration_ms` | Classification |
|---|---|---|
| `success` | > 0 | outer cycle (`_run_m4` or `_run_legacy`) |
| `success` | 0 | nested B2 phase (`run_b2:602`) |
| `shadow_failed` | 0 | **outer cycle**, aborted before Gold |
| `failed` | 0 | nested phase; **no outer record exists** for that cycle |

Two consequences the plan must carry:

1. The naive rule misclassifies `shadow_failed` — the safety-critical row — as a
   nested B2 metric. Any documented rule must be status-qualified.
2. **Recorded evidence contains only `status: success` rows.** The
   `shadow_failed` and `failed` branches are derived from reading the code, not
   observed. The documentation must say so rather than implying all four
   branches were verified against data.

### P1 — Proven no-op shadow fast path

- Do **not** skip on Bronze snapshot identity alone. Silver can move
  independently through recovery, and a Bronze-only check would skip validation
  that should run.
- Persist a shadow-comparison receipt containing at least: `bronze_snapshot_id`,
  `silver_snapshot_id`, runtime/cutover configuration identity,
  projection/business-contract version, comparison result, comparison timestamp.
- Skip the full Bronze scan, legacy rebuild and comparison **only when all hold**:
  current Bronze == certified Bronze; current Silver == certified Silver;
  runtime/projection contract unchanged; previous comparison succeeded.
- Any change to Bronze or Silver invalidates the fast path.
- When a comparison does run, preserve the existing pinned Bronze boundary
  (`_pin_bronze_boundary`) so the legacy candidate and the B2 result describe the
  same logical source.
- Recovery or independent Silver movement must force revalidation.

### P1 — Gold provenance / no-op rebuild

- Record which persisted Silver snapshot produced the current Gold state,
  preferably as Iceberg snapshot metadata (`source-silver-snapshot-id`) or an
  equivalent durable receipt.
- If Silver has not changed and Gold is already certified from that exact Silver
  snapshot, do not rebuild or overwrite Gold.
- Any Silver change must rebuild Gold.
- Recovery must not let stale Gold provenance masquerade as current.
- Note: the writer already stamps `snapshot_properties={"load-id": ...}` and
  re-checks it against snapshot summaries during recovery. Gold provenance is the
  same in-repo idiom, not a new mechanism. **Research confirmed the medallion
  already does exactly this on `overwrite`** — `iceberg_medallion.py:562-571`
  stamps `silver-work-id` and `:307-315` reads it back from snapshot summaries in
  a fresh process. `Table.overwrite()` accepts `snapshot_properties` in the pinned
  0.11.1. Two traps: a full overwrite writes **two** snapshots (delete + append,
  both stamped), and the append half is not elided for an empty frame.

### P2 — Steady-state shadow policy

- Analyse whether `SHADOW_COMPARE` must stay permanently enabled after a
  successful cutover.
- Do **not** simply add `(b2, persisted_silver, 0)` to `RUNTIME_ROLLOUT_MATRIX`.
- Define the evidence and safety conditions for moving from cutover validation to
  steady state. Candidate outcomes: permanent shadow, change-triggered shadow,
  sampled/periodic shadow, or shadow disabled after a certified cutover.
- Preserve rollback guarantees.

### P3 — Arrow/Python boundary, last

- Measure delta sizes and time in: Arrow→Python conversion, `collapse_delta`,
  `resolve_against_current`, Python→Arrow reconstruction.
- Optimise **only if still measurable** once redundant full-state work is gone.
- Prefer an Arrow-native/vectorised implementation before any other language.
- FF-14 semantics must be preserved exactly: same `order_id` + same
  `business_version` + different business payload ⇒ **reject**. This is a
  conflict detector, not an aggregation, and is not a mechanical `group_by`.

### Claude's Discretion

- Plan/task decomposition and commit boundaries.
- Whether the shadow receipt lives in Postgres, as Iceberg snapshot properties,
  or in writer-style state — provided it is durable and survives restart.
  **Correction:** the pre-planning claim that "the medallion has no durable state
  of its own" is **false**. It owns `streaming/medallion/progress.json` and an
  immutable per-load completion ledger in MinIO. What it lacks is a Docker volume.
  Research recommends: Gold provenance via a Gold snapshot property (reading
  `current_snapshot()` only, so Trino maintenance rewrites fail *safe*); shadow
  receipt in a new Postgres table on the `marts.maintenance_runs` precedent,
  because its identity spans three things and stamping it on Silver would violate
  the "Silver is not rewritten" contract.
- Metric schema mechanics (new columns vs a new table), provided historical rows
  stay interpretable.
- Test names and placement within the existing suite layout.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Code under change
- `iceberg/medallion/iceberg_medallion.py` — all six metric sites; `run_b2:444`,
  `_pin_bronze_boundary:941`, `_legacy_silver_cycle:958`, `_write_gold:1006`,
  `_run_legacy:1023`, `_run_m4:1047`, `run:1129`.
- `iceberg/common/ops.py` — `Metrics.record`, `marts.lakehouse_metrics` DDL.
- `iceberg/common/cutover.py` — `RUNTIME_ROLLOUT_MATRIX`, `validate_runtime_config`.
- `iceberg/b2_spike.py` — `collapse_delta`, `resolve_against_current`, FF-14.
- `iceberg/writer/iceberg_writer.py` — the `load-id` snapshot-property idiom to mirror.

### Contracts that must not regress
- `tests/features/silver_business_state.feature` — Silver business-state contract.
- `tests/features/shadow_cutover.feature`, `gold_cutover.feature`.
- `tests/features/writer_crash_recovery.feature`, `retention_recovery.feature`.
- `tests/test_b2_medallion.py`, `tests/test_m4_gold.py`, `tests/test_observability.py`.
- `docs/adr/0001-incremental-silver-and-gold.md`.
- `docs/remediation/M4-shadow-gold-cutover.md`, `M5-fitness-functions-and-cutover-gates.md`.

### Repository policy
- `AGENTS.md` — verification contract; no new tooling layer unless required.
- `CLAUDE.md` — stateful-service boundary; B2 rollout state machine.

</canonical_refs>

<specifics>
## Specific Ideas

### Required verification

Existing B2 Gherkin/business-state tests green; crash-before-commit and
crash-after-commit recovery green; replay/idempotency green; shadow mismatch
still fails closed; changing Bronze invalidates the receipt; changing Silver
independently invalidates the receipt; unchanged Bronze + unchanged Silver uses
the fast path; unchanged Silver skips the Gold rewrite; changed Silver rebuilds
Gold; metrics cannot double-count nested phase duration; before/after benchmark
on the same bounded workload.

### Required evidence artifact

Per measured cycle: `cycle_id`, phase durations, snapshot identities, whether
shadow executed or was skipped, whether Gold was rebuilt or skipped, total cycle
duration.

### Baseline that already exists

`artifacts/b2-rollout/06-o1-window.json` holds ten records = **five outer cycles**
under the corrected reading: totals 28.2 s, 50.5 s, 37.9 s, 34.5 s (the only
cycle with work: 1 file, 1 key, 4,422 bytes planned), 26.2 s. Gold cost 4.1–5.6 s
on every cycle including no-op ones. This is the before-measurement, but it is a
five-cycle sample at demo volume and establishes no scaling relationship.

</specifics>

<deferred>
## Deferred Ideas

- Any Rust component, including the Bronze writer. Unmeasured, not rejected.
- Replacing Spark Structured Streaming.
- Full-volume Olist load and the re-measurement it would justify.

</deferred>

---

*Phase: 04-medallion-telemetry-and-redundant-work-elimination*
*Context gathered: 2026-08-17 via PRD Express Path*
