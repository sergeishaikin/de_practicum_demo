## 1. Measure the boundary

- [x] 1.1 Read the code under measurement: `iceberg/b2_spike.py` in full, the production boundary at `iceberg/medallion/iceberg_medallion.py:605-635`, `_rows_to_silver` and `_SILVER_TYPES`, and `scripts/verify_m5_cutover.py` as the shape precedent
- [x] 1.2 Write `scripts/profile_arrow_boundary.py`: `main()` with `argparse`, JSON to `--out`, no live service, no catalog, no database, no MinIO, no Kafka
- [x] 1.3 Generate synthetic rows matching the Silver schema, parameterised by delta size, key cardinality and overlap ratio with current state, with payloads deterministic per `(order_id, business_version)` so no accidental FF-14 conflict is generated
- [x] 1.4 Measure the four steps separately: Arrow→Python on the delta and on the current scan, `collapse_delta`, `resolve_against_current`, and `_rows_to_silver` reconstruction
- [x] 1.5 Additionally measure the production call sequence as executed at lines 609-630, which collapses the delta twice, so the reported cost is one a real cycle actually pays
- [x] 1.6 Sweep at least four delta sizes spanning at least four orders of magnitude, reporting medians over a recorded repeat count, with key cardinality and overlap ratio recorded per measurement
- [x] 1.7 Record the environment: Python version, `pyarrow` version, platform, processor
- [x] 1.8 Emit `artifacts/phase-04/04-arrow-boundary-profile.json` in the `06-o1-summary.json` style, with a limits block stating what a synthetic microbenchmark does not reproduce
- [x] 1.9 Verify: script runs with no stack, at least four measurements present, `git diff --exit-code iceberg/` clean, ruff and black green on the new file

## 2. Decide against a rule fixed before the numbers

- [x] 2.1 Record the branch taken and the actual state of the denominator: `artifacts/phase-04/04-bench-summary.json` does not exist, because `04-09` was never authorised — named as absent, with no `disposition` or `reason` attributed to it and no stub created
- [x] 2.2 Record that the largest B2 delta in the whole committed evidence base is one key, one file, 4,422 bytes, from `06-o1-window.json` and `06-bounded-workload.json`
- [x] 2.3 Apply the pre-registered rule: `NOT WORTH DOING (unmeasurable baseline)` if the measured cost is negligible in absolute terms at every observed delta size, otherwise `INCONCLUSIVE`. `OPTIMISE` is unreachable on this branch
- [x] 2.4 Record the delta size at which the conclusion would flip, derived from the measurements rather than asserted
- [x] 2.5 Record the double-collapse finding with its measured cost, and mark it as requiring separate authorisation because a fix would change `iceberg/`
- [x] 2.6 Add a short cross-reference note to `docs/adr/0002-steady-state-shadow-policy.md` pointing at the profile artifact, without restating its contents
- [x] 2.7 Verify the artifact's shape: exactly one `disposition` from the allowed set, non-empty `reason`, flip point present, no fabricated denominator

## 3. Gates and closure

- [x] 3.1 Run `uv run --locked ruff check .`, `uv run --locked black --check .`, `uv run --locked pytest`, and the coverage gate; record the figures
- [x] 3.2 Confirm the scope fence: `git diff --exit-code iceberg/` clean, no new dependency, no stub `04-bench-summary.json` anywhere in the tree
- [x] 3.3 Write `evidence.md`: the measured numbers, the disposition and the rule it was chosen by, the Branch B adaptation as a documented deviation, and the double-collapse finding
- [x] 3.4 Commit atomically — remembering `git add -f` for the artifact, since `artifacts/` is gitignored — push, and confirm live CI is green on the pushed SHA
- [x] 3.5 Record the migration outcome for `04-10` in `.planning/STATE.md` as a ledger entry only
- [x] 3.6 Merge the spec delta, archive the change, and STOP — no further plan is begun without separate authorisation
