## 1. Analyse all fourteen, not just the one that surfaced

- [x] 1.1 Extract every item's `## Dependencies` section verbatim
- [x] 1.2 Apply one test to each declared edge: can the item be designed, implemented and evidenced without the dependency existing?
- [x] 1.3 Record the ten edges that pass and stay — NG-0.2, NG-0.3, NG-0.4, NG-0.5, NG-0.6, NG-0.7, NG-0.8, NG-1.3 — so unchanged rows are a result, not an omission
- [x] 1.4 Re-check the two already-recorded contradictions (NG-1.1, NG-1.2) and the newly found one (NG-0.9)
- [x] 1.5 NG-0.9: confirm nothing in it consumes an identity, dataset name, provenance envelope or telemetry label; confirm its architecture-fitness examples live in the index invariants rather than in NG-0.1
- [x] 1.6 Check the opposite failure: find any item gated too weakly. NG-2.2 reaches NG-0.3/0.5/0.6/0.7/0.8 only through NG-2.1's over-broad list

## 2. Correct the register

- [x] 2.1 Add NG-2.2's five explicit dependencies **before** trimming NG-2.1, so the graph is never briefly wrong
- [x] 2.2 NG-0.9 → no dependencies
- [x] 2.3 NG-1.1 → NG-0.1, NG-0.2, NG-0.4
- [x] 2.4 NG-1.2 → NG-0.1
- [x] 2.5 NG-2.1 → NG-0.1
- [x] 2.6 State what the column means: technical prerequisite, and what is excluded
- [x] 2.7 Move every preference, recommendation and "where available" relation into *Soft preferences, not gates*
- [x] 2.8 Replace the *Recorded contradictions* section — both are now resolved rather than pending
- [x] 2.9 Confirm row order is still a valid execution order without reordering rows
- [x] 2.10 Recompute the published layering from the validator's output, not by hand

## 3. Synchronise the item bodies

- [x] 3.1 NG-0.9 — no hard dependency, with the reason NG-0.1 had been listed
- [x] 3.2 NG-1.1 — hard vs not-gating, resolving its own required/recommended contradiction
- [x] 3.3 NG-1.2 — hard vs not-gating, noting its acceptance gates say "where available"
- [x] 3.4 NG-2.1 — hard vs not-gating, plus eligibility is not readiness
- [x] 3.5 NG-2.2 — five dependencies recorded explicitly, with why each is a tool it reads
- [x] 3.6 Verify no item body now disagrees with its register row

## 4. ADR-0003

- [x] 4.1 Check every wave against the corrected graph before editing anything
- [x] 4.2 Confirm the ADR's ordering is already consistent — no recommendation needs changing
- [x] 4.3 Restate the derived layering block from the validator's computation
- [x] 4.4 Restate the *Blocks* column from the corrected graph
- [x] 4.5 Normalise the order block so every execution slot is a bare item id; move annotations to prose below
- [x] 4.6 Amendment note recording what changed, what did not, and that only derived facts were restated
- [x] 4.7 Mark the reopen condition that fired — NG-1.1 confirmed not gated on NG-0.3 — and record that the recommendation was re-examined and kept

## 5. Make the defect class machine-detectable

- [x] 5.1 Register names its ordering document via a parseable pointer
- [x] 5.2 `validate_backlog.py` resolves that pointer and parses execution slots
- [x] 5.3 A slot is a bare item id alone on its line, so commentary can name an item without scheduling it
- [x] 5.4 Fail when an ordering places an item before a hard dependency, naming both positions
- [x] 5.5 Fail when an ordering omits an item or lists one twice
- [x] 5.6 Skip the check, rather than fail it, when a register names no ordering document
- [x] 5.7 `--repo-root` for anchoring, defaulting so the ordinary invocation needs no argument

## 6. Regression and negative proof

- [x] 6.1 `tests/test_backlog_validator.py` over synthetic registers, so the tests state the rule rather than an accident of the live files
- [x] 6.2 Positive: an ordering consistent with the graph passes, with the expected layering
- [x] 6.3 Negative: an ordering that inverts a hard dependency fails
- [x] 6.4 Negative: an item omitted from the ordering fails; an item ordered twice fails
- [x] 6.5 Negative: a named-but-missing ordering document fails
- [x] 6.6 Positive: prose naming an item is not an execution slot; no ordering pointer skips the check
- [x] 6.7 `architecture`-marked test that the live register and live ADR agree, and that NG-0.9 is layer 0
- [x] 6.8 Live negative proof: reintroduce the exact historical defect in the real files and record the message
- [x] 6.9 Live negative proof: drop an item from the real ADR ordering; move NG-0.7 ahead of NG-0.3
- [x] 6.10 Restore and confirm exit 0

## 7. Governance delta

- [x] 7.1 Requirement: a hard dependency is a technical prerequisite, with what SHALL NOT be recorded as one and why over-gating is not a safe default
- [x] 7.2 Scenario for the un-gating hazard found in NG-2.2
- [x] 7.3 Requirement: a published ordering respects the graph and is machine-checked across the two documents
- [x] 7.4 Scenario for an ordering left alone because it was already consistent
- [x] 7.5 Confirm neither restates an existing requirement in a driftable form

## 8. Gates and closure

- [x] 8.1 `uv run --locked ruff check .` and `uv run --locked black --check .`
- [x] 8.2 `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90`
- [x] 8.3 `uv run --locked python openspec/backlog/validate_backlog.py`
- [x] 8.4 `openspec validate reconcile-next-generation-hard-dependencies --strict` and `openspec validate --specs --strict`
- [x] 8.5 Scope fence: no runtime, Compose, dependency, CI or `.planning/` change; no `Authorised` cell moved
- [x] 8.6 Commit, push, and confirm all four live workflows
- [x] 8.7 `evidence.md`
- [x] 8.8 Archive, push, verify zero active changes and a clean tree
- [x] 8.9 Stop. `add-static-typing-gate` is now unblocked but remains unauthorised
