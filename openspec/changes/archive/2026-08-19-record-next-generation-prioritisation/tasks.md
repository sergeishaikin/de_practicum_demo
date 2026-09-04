## 1. Preconditions

- [x] 1.1 Confirm `add-next-generation-backlog` is archived and `openspec list` reports zero active changes — the operator's authorisation for this change was conditioned on it
- [x] 1.2 Confirm all fourteen backlog items still read `Authorised: no`, so this change is written against an unauthorised programme
- [x] 1.3 Read the register and re-derive the layering from `validate_backlog.py` rather than from the earlier chat analysis, so the ADR's layer table is machine-sourced
- [x] 1.4 Confirm the ADR numbering and filename follow the repository convention (`0002-steady-state-shadow-policy.md`), not the `ADR-0003-` form used informally

## 2. Write the ADR

- [x] 2.1 Header table in ADR-0002's shape: Status, Date, Deciders, Supersedes, Evidence base
- [x] 2.2 Put the normative statement **above** the context: priority is not authorisation; completing a prerequisite confers eligibility only; this ADR does not authorise NG-0.9; reordering requires an explicit amendment
- [x] 2.3 Context: what the register's row order does and does not encode, why the question arises now, and the machine-computed layering
- [x] 2.4 Decision: the four ranking axes, the per-item assessment table, the wave order, and the priority bands
- [x] 2.5 Decision 1 — NG-0.9 first, argued from decay and from lock-file ownership; note that NG-0.9 and NG-0.1 are sequenced rather than parallel
- [x] 2.6 Decision 2 — OM-PREFLIGHT as the first bounded gate *inside* `add-openmetadata-catalog`, with its pass/fail branches, and an explicit statement that it is not a new backlog item
- [x] 2.7 Decision 3 — NG-2.1 + NG-2.2 as one product slice delivered as two bounded changes, argued from NG-2.1's own product decision
- [x] 2.8 Decision 4 — the AI branch preferred over the streaming branch, with the comparison stating the streaming branch's value in its own terms rather than as a runner-up
- [x] 2.9 Parallelism policy: authoring concurrency bounded by file ownership, live-profile concurrency defaulting to one heavy profile, and an explicit prohibition on a combined mega-stack acceptance test
- [x] 2.10 Rename the delivery chain: "recommended path to the first differentiated end-state", not "critical path" — the programme has no fixed terminus, and four items may legitimately end in `DO NOT ADOPT`
- [x] 2.11 State that no measured profile receipt exists and every cost figure is relative
- [x] 2.12 Consequences, non-goals, and the conditions that would reopen the ordering

## 3. Fence and gates

- [x] 3.1 Verify `git diff --exit-code openspec/backlog/ openspec/specs/` is clean — this change records a view about the backlog and must not edit it
- [x] 3.2 Verify the two existing ADRs are unmodified
- [x] 3.3 Verify no runtime, test, CI, Compose or dependency file is touched
- [x] 3.4 Run `openspec validate record-next-generation-prioritisation --strict` and `openspec validate --specs --strict`
- [x] 3.5 Run the backlog structural check and confirm all fourteen items still read `Authorised: no` after the ADR lands
- [x] 3.6 Documentation-only change with no executable commands or configuration examples altered, so the Python completion gate does not apply; record that rather than implying it ran

## 4. Closure

- [x] 4.1 Write `evidence.md`: the fence result, the checks that ran, the checks that did not and why, and what was deliberately not done
- [x] 4.2 Commit and push
- [x] 4.3 Record the live CI outcome for the pushed SHA
- [x] 4.4 Archive the change; push the archive
- [x] 4.5 Verify the terminal state: zero active OpenSpec changes, clean working tree, fourteen items still `Authorised: no`
- [x] 4.6 Stop. This change authorises nothing; `add-static-typing-gate` — the item this ADR recommends first — requires its own decision
