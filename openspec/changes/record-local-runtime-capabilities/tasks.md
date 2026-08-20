## 1. Establish ground truth

- [x] 1.1 Check whether the Docker CLI exists and, separately, whether the engine responds
- [x] 1.2 Confirm Docker Desktop was running the whole time, contradicting earlier claims
- [x] 1.3 Measure host: OS, CPU model, logical CPUs, RAM, architecture
- [x] 1.4 Measure Docker: engine, Compose, backend, CPU/memory allocation, storage driver, disk usage
- [x] 1.5 Derive the Compose graph mechanically rather than transcribing it

## 2. Reconcile documentation against the real graph

- [x] 2.1 Enumerate locally built images; find that the documented list of four is actually six
- [x] 2.2 Discover the `.env` / `.env.example` image-pin drift and its two floating tags
- [x] 2.3 Establish why the committed-compose guard cannot see that drift
- [x] 2.4 Record the base-vs-extended Compose network conflict found while starting services

## 3. The diagnostic

- [x] 3.1 `scripts/local_runtime_inventory.py`, read-only, human and JSON output
- [x] 3.2 Distinguish "CLI absent" from "engine unreachable"
- [x] 3.3 Exit 0 when Docker is stopped; `--require-docker` for callers that need it
- [x] 3.4 Restrict env parsing to `*_IMAGE` keys so no secret can be captured
- [x] 3.5 Report image-pin drift against the committed example

## 4. Documentation

- [x] 4.1 `docs/LOCAL-ENVIRONMENT.md`: execution contract and decision rule
- [x] 4.2 The same document's measured snapshot, labelled as evidence
- [x] 4.3 `AGENTS.md`: normative Local runtime availability section
- [x] 4.4 `AGENTS.md`: redefine "available" at both places that used the word
- [x] 4.5 `docs/DEVELOPMENT.md`: container runtime, startup, inspection
- [x] 4.6 `docs/TESTING.md`: local-first policy and marker-to-runtime surface

## 5. Prove the procedure works

- [x] 5.1 Start the minimum Iceberg profile locally and wait for readiness
- [x] 5.2 Run the M5 live gates locally
- [x] 5.3 Run NG-0.1's receipt locally, testing the specific claim that it could not
- [x] 5.4 Measure the profile's resource cost while healthy
- [x] 5.5 Use the procedure to diagnose the NG-0.2 Airflow probe failure locally
- [x] 5.6 Verify the fixed probe against a live local Airflow
- [x] 5.7 Stop the services started for this work

## 6. Guards

- [x] 6.1 A stopped engine is reported, not raised
- [x] 6.2 Only image variables are read from env files
- [x] 6.3 Drift detection, and proof it can come out clean
- [x] 6.4 `.env.example` pins every image by digest
- [x] 6.5 The contract sentences are present in all four documents
- [x] 6.6 The generated inventory is not committed

## 7. Closure

- [x] 7.1 Correct the false locality claim in NG-0.1's archived evidence
- [x] 7.2 Confirm no secrets appear in the generated inventory
- [x] 7.3 ruff, black, mypy, pytest with the coverage gate
- [x] 7.4 Scope fence
- [ ] 7.5 Commit, push, confirm live CI
- [ ] 7.6 Evidence, archive, push
- [ ] 7.7 Resume the NG programme without further authorisation
