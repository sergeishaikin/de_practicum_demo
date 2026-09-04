---
phase: 4
slug: medallion-telemetry-and-redundant-work-elimination
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-18
---

# Phase 4 — Validation Strategy

Derived from `04-RESEARCH.md` Research Question 7.
Requirement IDs are `MTL-*`, not `TEL-*` — `TEL-01` is an already-Complete
Phase-1 requirement and reusing it would corrupt the traceability table.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 + pytest-bdd |
| Config file | `pytest.ini` — testpaths `tests`, pythonpath `.`, addopts excludes integration/e2e/airflow |
| Path shim | `tests/conftest.py:1-6` prepends `iceberg/`; imports are `medallion.iceberg_medallion`, `common.ops`, `b2_spike` |
| Quick run | `uv run --locked pytest -q tests/test_ops.py tests/test_b2_medallion.py tests/test_m4_gold.py tests/test_medallion.py` |
| Full suite | `uv run --locked ruff check . && uv run --locked black --check . && uv run --locked pytest` |
| Coverage gate | `uv run --locked pytest tests --cov=iceberg --cov-fail-under=90` — currently 93.66%, must not regress |
| PR-blocking extra | `ci-m5-gates.yml` runs BDD+integration on any `iceberg/**`, `tests/features/**` or `tests/support/**` change |

---

## Sampling Rate

- Per task commit: `ruff check .`, `black --check .`, plus the narrowest relevant test module.
- Per wave merge: full fast suite plus the `--cov-fail-under=90` gate.
- Any wave touching `iceberg/` or `tests/features/`: also the BDD+integration layer,
  because `ci-m5-gates.yml` will run it as a PR blocker regardless.
- Phase gate: AGENTS.md completion gate plus the before/after benchmark artifact.

---

## Per-Requirement Verification Map

| Req | Behaviour to prove | Layer | Exists? |
|-----|--------------------|-------|---------|
| MTL-01a | One logical run emits exactly one `phase=cycle` record | unit, FakeMetrics | yes |
| MTL-01b | All records from one run share one `cycle_id` | unit | yes |
| MTL-01c | Phase durations mutually non-overlapping; cycle >= sum of phases | unit, scripted monotonic | yes |
| MTL-01d | Nested B2 time not double-counted in Prometheus | unit, test_ops published() | yes |
| MTL-01e | Bronze/Silver/Gold snapshot ids recorded where meaningful | unit, fake current_snapshot | yes |
| MTL-01f | The cycle row is written LAST, protecting the exporter distinct-on-source | unit | yes |
| MTL-01g | Insert statement and DDL stay additive | unit, test_ops rewritten name-keyed | yes |
| MTL-02a | Status-qualified historical rule classifies all four branches | unit, executable classifier in `iceberg/common/` | module yes, fn no |
| MTL-02b | Docs state shadow_failed/failed branches derived from code, not observed | doc review | checkpoint |
| SHD-01a | Unchanged Bronze AND Silver leads to fast path, no legacy rebuild | unit | yes |
| SHD-01b | Changed Bronze invalidates receipt, comparison runs | unit | yes |
| SHD-01c | Silver changed independently invalidates receipt, comparison runs | unit | yes |
| SHD-01d | Changed runtime/projection identity invalidates receipt | unit, pure fn | yes |
| SHD-01e | Missing or unreadable receipt means comparison runs (fail-safe) | unit | yes |
| SHD-01f | A comparison that runs still uses the pinned Bronze boundary | existing test_m4_gold.py:174-188 stays green | yes |
| SHD-01g | Shadow mismatch still fails closed before any Gold write | BDD shadow_cutover.feature:41-47 | yes |
| SHD-01h | Receipt survives a process restart | integration, medallion_harness | after Wave 0 |
| GLD-01a | Unchanged Silver means Gold not rewritten | unit, FakeTable.overwrite_calls | yes |
| GLD-01b | Changed Silver means Gold rebuilt | unit | yes |
| GLD-01c | Gold write stamps source-silver-snapshot-id | unit, fakes.py captures it | yes |
| GLD-01d | Absent provenance forces rebuild, covering post-maintenance rewrite | unit | yes |
| GLD-01e | Provenance read from current_snapshot only, never older snapshots | unit, stale+bare snapshot seed | yes |
| GLD-01f | Provenance survives a real catalog round-trip | integration gold_cutover.feature | after Wave 0 |
| POL-01 | Steady-state shadow policy analysis | document, no test | n/a |
| PRF-01 | Arrow boundary measured; optimised only if measurable | artifact plus existing FF-14 tests | yes |
| REGR-1 | Crash-before and crash-after-commit recovery green | test_b2_medallion.py, test_m3_b2_recovery.py | yes |
| REGR-2 | Replay/idempotency green | writer_crash_recovery, retention_recovery | yes |
| REGR-3 | Silver business-state contract unchanged | silver_business_state.feature | yes |
| REGR-4 | Rollout matrix unchanged, P2 is analysis only | test_m5_fitness_functions.py -m architecture | yes |
| BENCH-01 | Before/after on the same bounded workload | artifact; needs live stack and authorised mutation | manual |

---

## Wave 0 Requirements — all block downstream work

- [ ] `tests/support/fakes.py` — add `FakeMetrics.phase(name)` and `.cycle()` accessors so
      assertions stop using `records[-1]`. Blocks every telemetry test.
- [ ] `tests/test_ops.py:116-143, 182-202` — convert positional insert-parameter
      assertions to name-keyed. Guaranteed break otherwise.
- [ ] `tests/support/medallion_harness.py:181-200` — replace `wait_for_new_gold_snapshot`,
      whose docstring asserts "Every cycle ends in a Gold overwrite". GLD-01 deletes that
      invariant, and gold_cutover.feature would then hang 90s per stage and fail the
      PR-blocking ci-m5-gates workflow. The replacement liveness signal must land in the
      SAME wave as GLD-01.
- [ ] `tests/test_m4_gold.py:76-89` — the local FakeTable lacks current_snapshot and
      discards snapshot_properties; extend it or switch to `tests/support/fakes.py`.
- [ ] Deterministic clock helper — scripted `m.time.monotonic`, so duration non-overlap is
      asserted on exact integers rather than timing luck.

No new framework, runner or wrapper script. AGENTS.md forbids adding a verification layer
the change does not require; nothing here requires one.

---

## Manual-Only Verifications

| Behaviour | Req | Why manual | Instructions |
|-----------|-----|-----------|--------------|
| Before/after benchmark | BENCH-01 | Needs a live stack and deliberate state mutation | Run the same bounded workload as `artifacts/b2-rollout/06-bounded-workload.json` pre- and post-change; emit the per-cycle evidence artifact. Authorised task only. |
| Docs honesty review | MTL-02b | Prose claim about provenance of evidence | Confirm docs say the shadow_failed/failed branches were derived from code, not observed |
| Steady-state policy | POL-01 | Analysis deliverable | Document evidence and safety conditions; do NOT change RUNTIME_ROLLOUT_MATRIX |

---

## Known Risks Carried From Research

- A full overwrite writes TWO snapshots (delete + append, both stamped), and the append
  half is NOT elided for an empty frame — "stamp-only empty overwrite" is a trap.
- The postgres exporter uses distinct-on-source; if the cycle row is not written last, a
  nested phase row becomes the exported latest state.
- Historical rows must stay interpretable: keep silver_duration_ms and gold_duration_ms
  populated only on the cycle row with today's inclusive meaning, so `cycle_id IS NULL`
  cleanly separates the two eras.

---

## Validation Sign-Off

- [ ] Every requirement row bound to a plan task
- [ ] Wave 0 gaps closed before dependent waves
- [ ] No watch-mode flags
- [ ] Coverage gate still at or above 90%
- [ ] nyquist_compliant true

**Approval:** pending
