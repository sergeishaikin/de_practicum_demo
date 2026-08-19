# B2 controlled rollout — result and DEC-01 decision

| | |
|---|---|
| **Requirement** | DEC-01 |
| **Frozen plan** | `.planning/phases/01-b2-controlled-rollout/01-07-PLAN.md` |
| **Executed as** | OpenSpec change `close-b2-rollout-decision` |
| **Decided** | 2026-08-19 |
| **Outcome** | **`no_change`** — one of `open_d3a` / `open_o2` / `no_change` |
| **Receipt** | [`07-rollout-decision.json`](07-rollout-decision.json) |

**What `no_change` means here.** D-3a (physical layout tuning) and O2 (tracing)
are **not opened now, on this evidence**. It is not a finding that either is
unnecessary. Both remain deferred with their reopen conditions recorded below,
and a future proposal is judged against those conditions, not against this
record's existence.

---

## The rollout, as it stands

Seven plans. The runtime finished the window in the `cutover` state and was not
changed by this decision:

```text
SILVER_MODE=b2   GOLD_SOURCE=persisted_silver   SHADOW_COMPARE=1   → cutover
```

Rollback was **not** executed during the window. It is recorded as verified by
`tests/integration/test_m4_gold_cutover.py` and by
[`05-rollback-receipt.json`](05-rollback-receipt.json), and explicitly **not**
invoked against the live runtime — recorded as it stands rather than as the
stronger claim.

## The evidence this decision consumed

All artifacts are historical and frozen. The observation window ran
**2026-08-10T19:50:06Z → 19:56:18Z**; nothing here re-ran it, started a service,
or produced new telemetry.

| Artifact | Role |
|---|---|
| [`06-telemetry-gate.json`](06-telemetry-gate.json) | the gate that makes the window usable — `PASS`, 13/13 checks, `failed_checks: []` |
| [`06-o1-summary.json`](06-o1-summary.json) | validity, counts, physical cost, per-row ratios — `valid: true`, `validity_reasons: []` |
| [`06-o1-window.json`](06-o1-window.json) | the raw metric rows |
| [`05-cutover-receipt.json`](05-cutover-receipt.json) | `CUTOVER_PASS`, runtime tuple, rollback status |
| [`06-o1-prometheus.json`](06-o1-prometheus.json) | 8 successful queries, correctness series present |
| [`06-bounded-workload.json`](06-bounded-workload.json) | the workload the window was observed under |
| [`../../docs/spikes/SPIKE-2-b2.md`](../../docs/spikes/SPIKE-2-b2.md) | layout baseline — cited, deliberately **not** compared; see the caveat |

Every entry in the receipt carries both a `sha256` of the working-tree bytes and
a `git_blob_sha1`, so the record can be verified on a machine whose checkout
normalises line endings differently.

### What was measured

```text
successful rows            10          (five outer cycles)
non-empty B2 rows           1
shadow comparisons          5
shadow mismatches           0
FF-14 conflicts             0
final work in flight        0
required fields complete    true
Prometheus queries          8 successful, correctness series present
```

Physical cost, from the single cycle that did work:

```text
files_planned  1     files_added  1     files_planned_per_added   1.0
bytes_planned  4422  bytes_added  4299  bytes_planned_per_added   1.028611
files_removed  0                        files_removed_per_added   0.0
bytes_removed  0                        bytes_removed_per_added   0.0
```

**Limits, stated where the figures are used:** one non-empty B2 cycle, demo
volume, one six-minute window. This establishes no scaling relationship and no
repeated pattern.

---

## Why `no_change`, and why not the other two

The outcome is computed. Each candidate is a conjunction of conditions stated in
the frozen plan; two of them fail on the artifacts' own recorded values.

### `open_d3a` — rejected, on two independent grounds

| Required condition | Held? |
|---|---|
| telemetry gate passed | ✅ |
| the window contains **repeated** non-empty B2 cycles | ❌ exactly one (`non_empty_b2_rows: 1`) |
| ratios show **material** scan/write amplification | ❌ `1.0` and `1.028611`, removals `0.0` |

Either failure is sufficient alone. The repetition condition is decided by a
count and needs no baseline comparison at all — which matters, because the
baseline comparison the plan asks for cannot be performed (see the caveat).

A ratio of 1.0 planned-to-added files with nothing removed is the **absence** of
amplification, not a small quantity of it.

*What would have had to be true:* several non-empty B2 cycles in a valid window,
showing a consistent planned-to-added or removed-to-added ratio materially above
1, with the operational impact of that ratio stated at the volume the system is
actually run at.

### `open_o2` — rejected

| Required condition | Held? |
|---|---|
| telemetry gate valid | ✅ |
| O1 records a real anomalous behaviour the captured fields cannot diagnose | ❌ no anomaly recorded at all |

`validity_reasons` is empty; shadow mismatches, FF-14 conflicts and final
in-flight work are all zero; required fields are complete; the corrected
Prometheus correctness series is present.

O2 exists to explain something observed and not understood. Nothing was observed
that is not understood, so there is no subject for tracing.

*What would have had to be true:* a concrete anomalous observation in a valid
window — a mismatch, a conflict, stuck in-flight work, or an unexplained cost —
that the recorded fields and raw rows cannot account for.

### `no_change` — selected

The residual branch: *amplification is not material, **or** O1 is sufficient*.
Both hold. The telemetry gate passed, so this is a decision made on valid
evidence rather than a fallback forced by an invalid window.

---

## Caveat — SPIKE-2 and O1 are not comparable

The frozen plan asks for material amplification *"relative to the documented
SPIKE-2 baseline"*. That phrasing presumes the two measurements are
commensurable. **They are not, and no comparison between them was performed.**

| Source | Quantity | Figures |
|---|---|---|
| SPIKE-2 | fraction of an existing table touched by a **read** | day: 10 files / 25.00%, 43,420 bytes / 25.14% · bucket: 27 files / 4.22%, 84,831 bytes / 4.24% |
| O1 | planned files and bytes against those **added by one write** | `files_planned_per_added` 1.0 · `bytes_planned_per_added` 1.028611 |

A scan-locality fraction and a write-amplification ratio share no denominator.
Dividing or ranking one against the other would manufacture a number with no
referent, and presenting it as a measurement would be worse than having none.
The `open_d3a` rejection therefore rests on the repetition condition, which is
independent of any baseline.

Recorded as a defect in the plan's wording rather than worked around silently.

---

## Deferred items and what would reopen them

### D-3a — physical layout tuning · **deferred, not refuted**

Reopen when **all** of the following hold:

1. a valid telemetry window contains several non-empty B2 cycles rather than one;
2. those cycles show a planned-to-added or removed-to-added ratio materially
   above 1, consistently rather than once;
3. the operational impact of that ratio is stated at the volume the system is
   actually run at, not at demo volume;
4. SPIKE-2's deferral rationale in ADR-0001 is revisited against that evidence.

### O2 — tracing · **deferred, not refuted**

Reopen when **both** hold:

1. a valid window records a behaviour the captured fields and raw rows cannot
   explain;
2. the missing explanation is identified specifically enough to say what a trace
   would have to show.

---

## Boundaries preserved

This decision opened no work and changed no system.

```text
implementation_changes   []
d3a_opened               false
o2_opened                false
historical_evidence      unmodified
live_stack_started       false
runtime changed          false
```

Out of scope and remaining so: D-3a implementation, O2 tracing, new
orchestration, multi-writer support, physical layout change, progress-protocol
change, and any production architecture change.
