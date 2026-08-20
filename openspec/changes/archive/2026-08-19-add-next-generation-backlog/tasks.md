## 1. The backlog surface

- [x] 1.1 Read the surfaces this one has to be distinguishable from: `openspec/specs/engineering-governance/spec.md` in full, `openspec/specs/verification-contract/spec.md`, the archived changes' shape, and the freeze note plus migration mapping in `.planning/STATE.md`
- [x] 1.2 Create `openspec/backlog/` with a `README.md` that tables all four planning surfaces (`specs/`, `changes/`, `backlog/`, `.planning/`) and states what a backlog item is not: not an authorisation, not evidence, not a plan, not a queue
- [x] 1.3 Confirm the README's claim about `.planning/` matches the governance spec rather than paraphrasing it loosely

## 2. Land the NG package

- [x] 2.1 Write `openspec/backlog/next-generation/00-INDEX.md`: purpose, execution order, dependency graph, thirteen cross-cutting invariants, Compose/profile policy, OpenSpec delivery contract, definition of program success
- [x] 2.2 Repair the mechanically damaged characters from the source text — mojibake for em dashes and arrows — and redraw the dependency graph in ASCII with the same edges, since its box-drawing characters did not survive transport
- [x] 2.3 Write the nine NG-0.x items: provenance contract, OpenLineage, OpenMetadata, OTel Collector, Tempo, Loki, Grafana correlation/SLO, data reliability, engineering quality gates
- [x] 2.4 Write the three NG-1.x items: Flink shadow streaming, ClickHouse hot analytics, Pinot real-time serving
- [x] 2.5 Write the two NG-2.x items: MLflow governance, evaluated incident agent
- [x] 2.6 Verify each item carries its own status header, execution-authorization line, scope, non-goals, requirements, acceptance evidence/gates, rollback and hard stops

## 3. Canonical register

- [x] 3.1 Replace the two overlapping tables (status/authorisation and execution order) with one register, so gate and dependency facts have exactly one home
- [x] 3.2 Document the column contracts inside the register itself — item id form, gate enum, dependencies as comma-separated ids, unique change id, `Authorised` as `no` or ISO date — so the parsing constraint is discoverable where the table is edited
- [x] 3.3 Normalise the dependency column to hard dependencies as item ids; move "preferably", "recommended" and prose qualifiers into a separate notes block where they cannot be read as gates
- [x] 3.4 Assign one change id per item, distinct, named for the work rather than the product where the outcome is conditional (`evaluate-*` for the five `EXPERIMENT` gates, `add-*`/`unify-*` for the nine `ADOPT` gates)
- [x] 3.5 Assert every `Authorised` cell reads `no`
- [x] 3.6 Record NG-1.1's internal contradiction (NG-0.3 listed as a dependency and called "recommended" in the same section) as unresolved, take the stricter reading in the register, and hand the resolution to `evaluate-flink-shadow-streaming`
- [x] 3.7 State the two ways a row may legitimately change, so a later editor does not use the register as a progress board

## 4. Freshness obligation

- [x] 4.1 Add an identical `## Freshness of external assumptions` section to all fourteen items, placed immediately after the normative-terms preamble so it conditions everything read below it
- [x] 4.2 Write it as WHEN/THEN/AND matching the items' existing scenario idiom, covering both re-verification at promotion and the case where a premise cannot be re-verified
- [x] 4.3 Keep it outside `## ADDED Requirements` — those requirements describe the future platform, whereas this one binds the promotion process
- [x] 4.4 Confirm insertion in all fourteen and normalise the blank line it introduced

## 5. Structural check

- [x] 5.1 Write `openspec/backlog/validate_backlog.py`: unique item ids, unique change ids across the backlog, resolvable dependencies, acyclic graph, row order valid as an execution order, authorisation cells constrained to `no` or an ISO date, referenced item files present and still carrying their unauthorised-future-work markers
- [x] 5.2 Make it discover every `*/00-INDEX.md` under the backlog root rather than hard-coding `next-generation`, so a second backlog is checked for free
- [x] 5.3 Compute the dependency layering from the register and publish it, so the index's layering is derived rather than drawn
- [x] 5.4 Replace the hand-made ASCII dependency graph with the derived layering; confirm the published layers match the validator's computation exactly
- [x] 5.5 Negative proof: mutate a scratch copy of the backlog seven ways — duplicate change id, dependency cycle, order violation, `Authorised` flipped to `yes`, unknown dependency, invalid gate value, freshness section removed — and record that each fails with a message naming the offence
- [x] 5.6 Restore the scratch copy and confirm it passes; confirm the real backlog was never mutated during the proof
- [x] 5.7 Record why the checker is a standalone script and not a pytest architecture fitness test: `tests/` is inside the authorised fence's forbidden set

## 6. Governance delta

- [x] 6.1 Requirement: recorded future work lives in the backlog and authorises nothing, with the change-id and authorisation-state obligations on the register
- [x] 6.2 Requirement: backlog ordering is not chained authorisation — completing an item confers eligibility, never permission, with a scenario binding autonomous execution explicitly
- [x] 6.3 Requirement: backlog premises are revalidated at promotion, including the case where a premise no longer holds
- [x] 6.4 Requirement: a register is structurally checkable, and any published diagram is derivable from it
- [x] 6.5 Requirement: a backlog contradiction stops the change that finds it — resolution happens as a bounded backlog correction or a recorded authoritative interpretation, never inside the implementing change's design
- [x] 6.6 Rework the register's contradiction note accordingly: label the stricter readings as **interim interpretations**, record both defects (NG-1.1 and NG-1.2) rather than only NG-1.1, and drop the earlier "resolve in design" wording
- [x] 6.7 Confirm none of the five restates "authorisation is explicit and per change" in a second, driftable form

## 7. Authorisation record and pointers

- [x] 7.1 Record the operator's authorisation in `proposal.md`: this change only, with the fourteen items listed as not authorised
- [x] 7.2 Correct the earlier "nothing is authorised" wording explicitly rather than leaving the contradiction to be inferred
- [x] 7.3 Add the backlog to `AGENTS.md` → Planning methodology
- [x] 7.4 Add the backlog to `CLAUDE.md` → Working rules, alongside the existing `openspec/` and `.planning/` bullets
- [x] 7.5 Add the promotion contract and the structural-check command to the backlog README

## 8. Gates and closure

- [x] 8.1 Run `uv run --locked ruff check .` and `uv run --locked black --check .` — this change now adds a Python file, so the completion gate applies
- [x] 8.2 Run `uv run --locked pytest` and the coverage gate; confirm the added script changes neither
- [x] 8.3 Run `uv run --locked python openspec/backlog/validate_backlog.py`
- [x] 8.4 Run `openspec validate add-next-generation-backlog --strict` and `openspec validate --specs --strict`
- [x] 8.5 Verify the scope fence: `git status` shows no modification under `iceberg/`, `dags/`, `dbt/`, `spark/`, `kafka/`, `observability/`, `tests/`, `scripts/`, `.planning/`, and no Compose, `pyproject.toml`, lock or CI workflow edits
- [x] 8.6 Write `evidence.md`: gate figures, the negative proof, what was carried across unchanged, and what was deliberately not done
- [x] 8.7 Commit and push
- [x] 8.8 Record whether live CI ran on the pushed SHA, and if it did not, say so rather than implying a green gate
- [x] 8.9 Archive the change, merging the spec delta into `openspec/specs/engineering-governance/spec.md`; push the archive
- [x] 8.10 Verify the terminal state: zero active OpenSpec changes, clean working tree, all fourteen items `Authorised: no`
- [x] 8.11 Stop. Completing this change authorises nothing; `add-platform-provenance-contract` requires its own decision
