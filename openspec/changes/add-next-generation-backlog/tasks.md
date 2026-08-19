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

## 3. Status and authorisation table

- [x] 3.1 Add the status/authorisation table to `00-INDEX.md`: item, capability, decision gate, dependencies, pre-assigned change id, `Authorised`
- [x] 3.2 Assign one change id per item, distinct, and named for the work rather than the product where the outcome is conditional (`evaluate-*` for the four `EXPERIMENT` gates, `add-*`/`unify-*` for the ten `ADOPT` gates)
- [x] 3.3 Assert every `Authorised` cell reads `no`
- [x] 3.4 State the two ways a row may legitimately change, so a later editor does not use the table as a progress board

## 4. Governance delta

- [x] 4.1 Add one requirement to `engineering-governance`: recorded future work lives in the backlog and authorises nothing, with the change-id and authorisation-state obligations on the index
- [x] 4.2 Give it the three scenarios that cover the failure modes: item picked up, backlog `SHALL` quoted as current behaviour, item that looks too small to need authorisation
- [x] 4.3 Confirm the new requirement does not restate "authorisation is explicit and per change" in a second, driftable form

## 5. Pointers and closure

- [x] 5.1 Add the backlog to `AGENTS.md` → Planning methodology
- [x] 5.2 Add the backlog to `CLAUDE.md` → Working rules, alongside the existing `openspec/` and `.planning/` bullets
- [x] 5.3 Verify the scope fence: `git status` shows no modification under `iceberg/`, `dags/`, `dbt/`, `spark/`, `kafka/`, `observability/`, `tests/`, `scripts/`, `.planning/`, and no Compose, `pyproject.toml`, lock or CI workflow edits
- [x] 5.4 Write `evidence.md`: what was verified against the repository, what was carried across unchanged, and what was deliberately not done
- [x] 5.5 Stop. No backlog item is authorised by this change; NG-0.1 requires its own decision
