## 1. Select the item and re-verify its premises

- [x] 1.1 Re-read the register and ADR-0003 after NG-0.1 archived; confirm NG-0.2 is the next eligible `ADOPT` item
- [x] 1.2 Re-verify the Airflow provider premise against primary sources
- [x] 1.3 Re-verify the Spark integration premise against the integration's own build configuration
- [x] 1.4 Re-verify the transport options, and whether a backend is required for a receipt
- [x] 1.5 Probe the Airflow dependency resolution before designing around it
- [x] 1.6 Record all five verdicts in the design, including the two refutations

## 2. The naming and emission contract

- [x] 2.1 `iceberg/common/lineage.py`: `DatasetRef` and endpoint normalisation
- [x] 2.2 Kafka, object-store and Iceberg dataset constructors
- [x] 2.3 The edge-ownership registry, raising on a second claimant
- [x] 2.4 The fail-open emitter, with a failure counter
- [x] 2.5 Run facets built from an NG-0.1 `ProvenanceEnvelope`
- [x] 2.6 Confirm the module enters typed scope and passes mypy

## 3. First-party emitters

- [x] 3.1 Writer emits `landing → bronze.orders` with the real `load_id` and resulting snapshot id
- [x] 3.2 Medallion emits `bronze → silver` with the real `cycle_id` and snapshot ids
- [x] 3.3 Medallion emits `silver → gold`
- [x] 3.4 Confirm no processing semantics changed at any of the three sites

## 4. Airflow

- [x] 4.1 Add `apache-airflow-providers-openlineage==2.20.0`, regenerating the lock in place so no unrelated pin drifts
- [x] 4.2 Configure transport and namespace; confirm the lineage volume is shared
- [x] 4.3 Confirm the DagBag still builds

## 5. Tests

- [x] 5.1 Naming determinism, including the endpoint-spelling and container-id cases
- [x] 5.2 The duplicate-edge negative test
- [x] 5.3 Backend-down: processing result unchanged, failure counted
- [x] 5.4 An emitter that raises does not reach the data path
- [x] 5.5 Captured event JSON: shape, identifiers, declared absences
- [x] 5.6 Prove each guard can fail, or the passing tests prove nothing
- [x] 5.7 Integration receipt: read emitted events out of the running stack and assert the connected path

## 6. Documentation

- [x] 6.1 `docs/LINEAGE.md`: the naming contract, ownership, failure rules
- [x] 6.2 The Spark blocker with its primary-source evidence
- [x] 6.3 The `Kafka → landing` gap, named as a gap
- [x] 6.4 `AGENTS.md` pointer

## 7. Gates and closure

- [x] 7.1 ruff, black, mypy, pytest with the coverage gate
- [x] 7.2 Confirm coverage did not fall
- [x] 7.3 Scope fence
- [x] 7.4 Flip NG-0.2's register row
- [ ] 7.5 Commit, push, confirm live CI
- [ ] 7.6 Evidence, archive, push
- [ ] 7.7 Re-read canonical sources and select the next programme item
