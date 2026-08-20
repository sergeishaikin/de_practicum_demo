## 1. Select the item from live sources

- [x] 1.1 Re-read the register and ADR-0003 after NG-0.9 archived, rather than following a plan made earlier in the programme
- [x] 1.2 Confirm NG-0.1 is `ADOPT`, Wave 1, and has no hard dependency
- [x] 1.3 Inventory what identity the platform already carries: `cycle_id`, `load_id`, snapshot properties, Kafka position columns on Bronze
- [x] 1.4 Confirm the invariants the contract will assert already hold — no `latest` in committed Compose, no high-cardinality Prometheus label — so the tests pin behaviour rather than demand a change

## 2. The contract document

- [x] 2.1 `docs/PROVENANCE.md`: vocabulary table naming what each identifier is authoritative for and who owns it
- [x] 2.2 Argue why identifiers are linked rather than merged — a `trace_id` is discarded by telemetry, and merging would make correctness depend on a control plane the platform must survive without
- [x] 2.3 The never-fabricate rule, and why an absent field carries a reason
- [x] 2.4 Iceberg snapshot as the version primitive, and the consequent decision that DVC and lakeFS are not adopted
- [x] 2.5 Cardinality rules, naming where high-cardinality identity may legitimately go
- [x] 2.6 Data-plane / control-plane separation, images, secrets, profile isolation
- [x] 2.7 A section stating what the contract does **not** yet cover, so absence is not read as completeness

## 3. The executable half

- [x] 3.1 `iceberg/common/provenance.py` with the canonical field constants and `CANONICAL_FIELDS`
- [x] 3.2 `HIGH_CARDINALITY_FIELDS` and `FORBIDDEN_LABEL_NAMES` — bare label spellings, case-insensitive, including the business key
- [x] 3.3 `ProvenanceEnvelope` that raises on a null value, a field both known and unknown, an unknown without a reason, and a name outside the vocabulary
- [x] 3.4 `requires()` so a boundary contractually complete can fail at the boundary
- [x] 3.5 Immutability, and `to_dict()` returning a copy
- [x] 3.6 `cardinality_violations()` returning every offender, and rejecting a bare string rather than iterating it by character
- [x] 3.7 Confirm the module enters typed scope automatically and passes `mypy` — it did, and mypy rejected an unnecessary suppression in it

## 4. Tests

- [x] 4.1 Envelope: absence with a reason; null refused; both-known-and-unknown refused; reasonless unknown refused; unrecognised name refused; `requires` enforced; immutable
- [x] 4.2 The negative test the item requires: parse every Prometheus metric declaration in `iceberg/common/ops.py` and `observability/postgres_exporter.py`, fail on a forbidden label name
- [x] 4.3 Guard the guard: assert the listed metric sources exist, so a rename fails loudly rather than checking nothing
- [x] 4.4 Prove the cardinality check can fail, or the passing test proves nothing
- [x] 4.5 `architecture`: the writer stamps `load-id` into the snapshot — the hop that joins transport position to stored state
- [x] 4.6 `architecture`: no floating `latest` in committed Compose
- [x] 4.7 Integration receipt: Kafka position read off the row, the snapshot carrying that `load-id`, an envelope that refuses the two identifiers this boundary lacks, and the receipt written out

## 5. Gates and closure

- [x] 5.1 ruff, black, mypy, pytest with the coverage gate
- [x] 5.2 Confirm coverage did not fall
- [x] 5.3 Confirm the integration test collects, and record that it cannot run locally — no live stack, and starting one is not authorised
- [x] 5.4 Scope fence
- [x] 5.5 `AGENTS.md` gains a Provenance section
- [x] 5.6 Flip NG-0.1's register row to its authorisation date
- [x] 5.7 Commit, push, confirm live CI
- [x] 5.8 Evidence, archive, push
- [x] 5.9 Re-read canonical sources and select the next programme item
