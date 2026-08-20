## Verification receipt

Commit under test: `772762e` — *feat(provenance): add the platform identity and provenance contract*

All four workflows that trigger for this branch ran on this exact SHA and
succeeded. No workflow was skipped, cancelled or superseded.

| Run | Workflow | Conclusion |
|---|---|---|
| [32347175301](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32347175301) | CI | success |
| [32347175292](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32347175292) | M5 architecture gates | success |
| [32347175348](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32347175348) | S1 dbt semantic lineage | success |
| [32347175323](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32347175323) | H1 clean reproducible stack | success |

### The repository verification contract, per step

From run `32347175301`:

```
Ruff                                            All checks passed!
mypy (typed scope declared in pyproject.toml)   Success: no issues found in 8 source files
Fast unit suite with coverage gate (>= 90%)     434 passed, 71 deselected
                                                Required test coverage of 90% reached. Total coverage: 94.48%
```

Coverage rose from 94.29% to **94.48%**. It did not fall, which task 5.2 required.

The mypy step reports **8** source files. Before this change it reported 7.
`iceberg/common/provenance.py` entered typed scope with no configuration
change, because NG-0.9 declared the scope by package rather than by file list.
That was the property NG-0.9 claimed, observed here on the next item rather
than asserted about itself.

### The receipt ran against a live stack

The end-to-end receipt is the acceptance evidence NG-0.1 actually asks for, and
it is only meaningful against real state. It could not run locally — no live
catalog or object store here, and starting one is outside this change's scope —
so locally it was confirmed to collect, and it executed for real in CI.

From run `32347175323`, the H1 integration suite:

```
tests/integration/test_provenance_receipt.py .                           [ 69%]
============ 25 passed, 1 xfailed, 10 warnings in 239.67s (0:03:59) ============
```

That single dot is the chain verified against a live REST catalog and object
store: a Kafka position read back off the stored Bronze row, the one snapshot
whose summary carries that append's `load-id`, and its `snapshot_id` — each hop
read out of the platform rather than asserted.

The envelope in that test declares `dag_run_id` and `trace_id` **unknown, with
reasons**, and the test asserts neither appears in `to_dict()`. So the run also
proves the negative half of the contract: at a boundary that genuinely lacks two
identifiers, nothing was invented to fill them.

### Scope fence

```
git diff --exit-code dags/ dbt/ spark/ kafka/ observability/ scripts/ .planning/ \
  docker-compose.yml docker-compose.extended.yml pyproject.toml uv.lock
```

Clean. No runtime behaviour changed: no metric, label, schema or snapshot
property was touched, no dependency or service was added. The three green
non-CI workflows corroborate this from the other direction — M5 gates, S1 dbt
and the full H1 clean-stack rebuild all pass unchanged.

### What this change did not prove

Recorded so the green result is not read as more than it is.

- **No production boundary emits an envelope.** `ProvenanceEnvelope` is
  exercised by its tests and the receipt. Retrofitting the writer and medallion
  to emit one is per-boundary behaviour work, deliberately not done inside a
  contract change. `docs/PROVENANCE.md` says so under what the contract does
  not yet cover.
- **The cardinality test reads declarations, not runtime.** It AST-parses the
  metric declarations in `iceberg/common/ops.py` and
  `observability/postgres_exporter.py`. A label assembled at runtime from a
  variable would not appear as a string constant and would not be caught. All
  ten label sets in this repository are literals today; if that changes the
  test needs extending.
- **`platform.run_id` has no producer.** The vocabulary reserves the name and
  nothing emits one.

### A guard that earned itself

`test_the_metric_sources_this_test_guards_actually_exist` exists so a renamed
metrics module fails loudly instead of leaving the cardinality check silently
scanning nothing. The first draft of the check pointed at
`observability/exporter.py`, which does not exist. The guard failed and the
path was corrected before commit — the failure mode it was written for,
occurring immediately.
