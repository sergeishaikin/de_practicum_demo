# Evidence — close-b2-rollout-decision

## The decisive conditions

The outcome was computed, not chosen. Each candidate is a conjunction stated in
the frozen plan; two fail on values the artifacts already record.

| Outcome | Condition that decided it | Value |
|---|---|---|
| `open_d3a` | repeated non-empty B2 cycles | `non_empty_b2_rows: 1` — one, so no repetition exists |
| `open_d3a` | material amplification | `files_planned_per_added 1.0`, `bytes_planned_per_added 1.028611`, removals `0.0` |
| `open_o2` | a real undiagnosed anomaly | none recorded: `validity_reasons: []`, mismatches 0, FF-14 0, in-flight 0, fields complete |
| `no_change` | "amplification not material **or** O1 sufficient" | both hold, on a gate that passed |

`open_d3a` fails on two independent grounds, either sufficient alone. The
repetition condition is decided by a count, which matters because the baseline
comparison the plan asks for cannot be performed — see the deviation below.

## Evidence integrity

Every artifact the decision consumed was hashed twice and verified
programmatically against the files after the receipt was written:

```text
OK   artifacts/b2-rollout/05-cutover-receipt.json
OK   artifacts/b2-rollout/06-o1-window.json
OK   artifacts/b2-rollout/06-o1-summary.json
OK   artifacts/b2-rollout/06-telemetry-gate.json
OK   artifacts/b2-rollout/06-o1-prometheus.json
OK   artifacts/b2-rollout/06-bounded-workload.json
OK   docs/spikes/SPIKE-2-b2.md
all evidence hashes verified: True
```

`sha256` covers the working-tree bytes; `git_blob_sha1` is the content-addressed
blob id, which survives checkout line-ending normalisation.

**One correction made during the work.** The first draft of the receipt carried a
`PLACEHOLDER` git blob id and an unverified sha256 for `SPIKE-2-b2.md`. Both were
computed from the file and substituted, and the verification above was then run
over the whole evidence list rather than over the corrected entry alone. A
provenance record with an invented hash is worse than one with no hash, because
it presents as verifiable.

## Gate output, verbatim

The frozen plan's own automated verifications:

```text
$ python -c "... assert p['outcome'] in {...}; assert isinstance(p.get('evidence'),list) and p['evidence']"
DEC-01 outcome shape PASS

$ python -c "... assert set(p['rejected_outcomes'])==allowed-{p['outcome']}; assert p['implementation_changes']==[]"
decision schema PASS

$ python -c "... assert 'B2 Controlled Rollout' in roadmap and 'D-3a' in state and 'O2' in state"
rollout status traceability PASS
```

Repository gates:

| Command | Result |
|---|---|
| `uv run --locked ruff check .` | `All checks passed!` |
| `uv run --locked black --check .` | `71 files would be left unchanged` |
| `uv run --locked pytest` | `398 passed, 63 deselected` |
| coverage gate, `--cov-fail-under=90` | `Total coverage: 94.28%` |

**Confirming CI on `25d240c`** — checked before closure, as task 3.3 requires:
`H1 clean reproducible stack`, `CI`, `M5 architecture gates` and
`S1 dbt semantic lineage` all `success`. It exercises the test suites, not the
frozen 2026-08-10 window, so it could not have invalidated the 01-07 inputs; it
was checked rather than assumed.

No test was added or changed by this change. The suite figures are unchanged
from the previous commit, which is the expected result for a decision record.

## Deviations from the frozen plan

1. **`.planning/ROADMAP.md` was not edited.** The plan's Task 2 instructs
   updating both `STATE.md` and `ROADMAP.md` as live project state. That
   instruction predates the 2026-08-18 cutover, after which
   `engineering-governance` treats `.planning/` as historical evidence editable
   only as a migration ledger. The instruction's *intent* — that the outcome be
   traceable from project state — is met by the ledger entry, which names the
   outcome and points at this change and at the receipt. The plan's own
   automated check for Task 2 asserts only that the strings `D-3a`, `O2` and
   `B2 Controlled Rollout` appear in those files; they already do from
   pre-freeze history, so the check passes without an edit. Recorded rather than
   quietly satisfied.

2. **The SPIKE-2 baseline comparison the plan asks for was not performed.**
   `open_d3a` is defined as material amplification *"relative to the documented
   SPIKE-2 baseline"*. SPIKE-2 measures the fraction of an existing table touched
   by a read (day 25.00%, bucket 4.22%); O1 measures planned files and bytes
   against those added by one write (1.0, 1.028611). The two share no
   denominator, and combining them would manufacture a number with no referent.
   The receipt records both figures, states `"compared": false` with the reason
   as a field rather than as prose only, and rests the rejection on the
   repetition condition, which needs no baseline. This is a defect in the plan's
   wording, not in the evidence.

## Discovery worth recording

**`artifacts/` is gitignored, and the b2-rollout evidence is tracked only
because it was force-added.** `.gitignore:63` ignores the directory; `git
ls-files` shows the existing artifacts as tracked, added in `3219c9c`. A plain
`git add -A` therefore leaves a new receipt untracked and silently uncommitted,
and `git status --porcelain artifacts/b2-rollout/` reports nothing — which reads
exactly like "no changes". The two new files were added with `git add -f`,
matching the established convention. Anyone writing a future receipt under
`artifacts/` needs to know this or the artifact will not survive the commit.

## Scope fence, verified

| Fence | Check | Result |
|---|---|---|
| No D-3a or O2 implementation | `implementation_changes == []`, asserted | holds |
| Deferred items not opened | `d3a_opened: false`, `o2_opened: false` | holds |
| Historical evidence unmodified | `git status --porcelain artifacts/b2-rollout/` showed no modifications to existing files | holds |
| No live stack started | none required, none started; the window is frozen and dated 2026-08-10 | holds |
| No source change | no file under `iceberg/`, `spark/`, `dags/` or `dbt/` touched | holds |
| `04-09` untouched, `04-10` not begun | no benchmark or Arrow/Python work | holds |
