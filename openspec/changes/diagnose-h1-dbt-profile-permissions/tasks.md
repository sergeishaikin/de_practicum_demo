## 1. Observe ownership on the runner

- [ ] 1.1 Add an unconditional, read-only probe step to `.github/workflows/ci-h1-clean.yml` immediately before `dbt semantic contract`, every command `|| true` so it cannot change the run outcome
- [ ] 1.2 Have the probe print `id`, `ls -ld .`, `ls -ld dbt`, `ls -la dbt`, `stat dbt`, `stat dbt/profiles.yml` (tolerating absence), `stat dbt/profiles.yml.example` and `find dbt -maxdepth 1 -printf '%u:%g %m %p\n'`
- [ ] 1.3 Have the probe also record the effective compose mounts and container user for every service that mounts `dbt/`, so the mutation can be attributed to a named service rather than inferred
- [ ] 1.4 Include the probe output in the existing artifact upload, so the observation survives the run
- [ ] 1.5 Push and let the H1 run that this push triggers carry the probe — do not spend a dedicated run

## 2. Establish provenance

- [ ] 2.1 Record the probe output verbatim in `evidence.md` in this change
- [ ] 2.2 Classify as A (a `profiles.yml` exists, owned by a container UID), B (`dbt/` itself is unwritable to the runner), or C (no container mutation — a workflow or checkout contract problem)
- [ ] 2.3 If the observation contradicts the predicted case A, stop and revise `design.md` before any fix is written

## 3. Fix at the owner of the mutation

- [ ] 3.1 Apply the minimal correction indicated by the established case, at the owner of the host-state mutation — not at the `cp`
- [ ] 3.2 Keep `/opt/airflow/project/dbt/profiles.yml` resolvable for both Cosmos `ProfileConfig` call sites, since `dags/warehouse_dbt.py` and `dags/lakehouse_dbt_semantic.py` name that path
- [ ] 3.3 Run the repository completion gate, plus `pytest tests/test_dags.py -m airflow` if the change touches anything the DagBag reads
- [ ] 3.4 Confirm no `chmod`, `chown`, `sudo`, retry or sleep was introduced

## 4. Prove and close

- [ ] 4.1 Let the next H1 run show the probe reporting `dbt/` owned by the runner and `dbt semantic contract` getting past the `cp`
- [ ] 4.2 Record the before/after probe output as the demonstration that the fix worked
- [ ] 4.3 If H1 then fails at a later step, record it as the next layer with its step and message — do not extend this change to cover it
- [ ] 4.4 Update `.planning/STATE.md`'s migration ledger only if this change closes an obligation listed there; otherwise leave it untouched
