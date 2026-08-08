# Coverage and limitations — audit baseline

Companion to `synthesis.md`. This file exists separately because
`verify-architecture-remediation` compares scope before it compares findings: **if the scope of a
later audit differs materially from what is recorded here, the comparison must be marked
`INCOMPARABLE` rather than reported as improvement or regression.**

- **Repository revision at capture:** `d20b2062`, branch `feature/extended-local-stack`
- **Profile:** `standard` container, deliberately narrowed run
- **Baseline digest:** see `../README.md`

---

## Declared scope

> Only architecture bearing on moving Silver and Gold from full-overwrite to incremental
> processing.

**This is not a full architecture review and must not be read as one.**

## Phases

| Run | Not run |
|---|---|
| 01 discovery | 04 clean / hexagonal |
| 02 intent reconstruction | 05 modularity and SOLID |
| 03 dependency boundaries | 06 domain-driven design |
| 07 data and integration | 08 security architecture |
| 10 testability and evolution | 09 quality attributes |
| 11 synthesis | 12 remediation planning |
| | 13 documentation generation |
| | verification |

Phases 07, 10 and 11 ran **outside the audit state machine**. The state machine enforces the
standard phase order and would have required 04, 05 and 06 first; those are outside the declared
scope and were deliberately skipped. Ordering is recorded inside each artifact instead. The
working state file remains at revision 3, 3 of 13 complete.

## Paths

**In scope:** all tracked source, configuration, SQL, DAGs, tests and CI under the repository
root. `temp-stack-tools`, `.testagent` and `.scripts` are in scope — they are tracked in git.

**Excluded:** `.trunk`, `.agents`, `.claude`, `.planning`, `artifacts`, `imgs`, plus scanner
defaults (`.git`, `__pycache__`, `node_modules`, `.venv`, `dist`, `build`, …).

> `--exclude` **augments** the scanner's default list rather than replacing it, and is not
> persisted between invocations. The exclusion set above must be passed on every re-run or the
> inventory is not reproducible. A first run without `.trunk` counted 1496 files and reported 224
> TypeScript files in a Python/SQL repository.

Reproduce the inventory with:

```
aak inventory --root . --out <path> \
  --exclude .trunk --exclude .agents --exclude .claude \
  --exclude .planning --exclude artifacts --exclude imgs
```

## Scale at capture

117 files in scope · 63 classified as code · 62 parsed (ratio 0.9841) · 8 test files.

## Rule coverage

- **Declared rules evaluated:** 7 of 9. Not evaluated: AR-001 (catalog access uniformity),
  AR-006 (best-effort observability) — neither bears on the boundary question.
- **ADRs in the repository at capture:** **0.** Every declared rule was reconstructed from
  `docs/ARCHITECTURE.md`, the single prose source.
- **Boundaries evaluated:** B-002 … B-007, B-009. Not evaluated: B-001 (Kafka, upstream of the
  change surface), B-008 (Spark checkpoints, single owner, untouched by this transition).

## Scoring — suppressed

**Conformance scoring is suppressed.** Zero ADRs and one prose source make declared-rule coverage
insufficient for any conformance percentage.

**`riskIndex` is 100.0 and must not be cited.** It is a saturated arithmetic aggregate over 28
findings from a deliberately narrow, high-intensity audit of one change surface. It is not a
quality grade and is not comparable to any other repository or to any differently-scoped run of
this one.

## Analysis method

- **Boundary model:** data-plane and infrastructure-plane, **not** import-plane. The inventory
  reported `internalEdgeCount: 0` against `unresolvedImportCount: 159`. Exactly one internal
  import edge exists (`common.ops`, fan-in 2) and it is constructed by runtime `sys.path`
  mutation, so no static tool resolves it. Import-based boundary analysis would report "no
  violations" as an artefact of the method.
- **Sampling:** exhaustive over the 22 Python files, both compose files, `db/init/*.sql`,
  `db/tasks/*.sql`, `trino/etc/`, all three CI workflows and all 8 test files.
- **Library introspection:** the pyiceberg API surface was checked against the locally installed
  0.11.1, which matches the pin in `iceberg/Dockerfile:3`. **Not** introspected inside the
  container.

## Rule families skipped, with reasons

| Family | Reason |
|---|---|
| Import cycles, layer direction, instability metrics, transitive paths | Require a resolvable module graph; none exists (see boundary model) |
| Privacy classification, retention and deletion of personal data | Synthetic generated data only; no real subjects |
| CDC semantics | No CDC exists in this system |
| API contract versioning | No synchronous service API; Trino and JDBC are query surfaces, not versioned contracts |
| Kafka backpressure and DLQ tuning | Outside the declared scope |
| Mutation testing execution | No tooling present; recommended as a one-off experiment, not adopted |
| Performance budgets | No benchmark suite exists; none proposed beyond the scan-volume measure |
| Security fitness functions | Deferred — the security audit was not run |

## Dynamic behaviour — not observed

**Nothing in this baseline was reproduced against a running stack.** All behavioural claims are
static, derived from source, configuration and CI definitions.

- No live stack was started in any phase.
- No test was executed and no CI run was triggered.
- No orphan landing file, commit conflict, duplicate append or concurrency window was reproduced.
- Spark file-sink commit semantics were taken from documented behaviour, not measured — this is
  why F-703 carries `confidence: medium` despite `severity: high`.
- Runtime wiring, reflection, generated code and build-time transforms were not observed.

## Compliance

**No compliance claim is issued.** Five specialist audits were deliberately not run. **Absence of
a finding in this baseline is not evidence of absence of the problem.**

## Known unexamined alternative

Moving the medallion off pyiceberg to Spark or Trino would provide engine-native change tracking
and would make F-701, F-704 and much of decision D-2 irrelevant. It was out of scope because the
architecture profile fixed the medallion as a pyiceberg process. **It was never evaluated.** This
is the largest single gap in the baseline and is recorded here rather than buried.

## Tool errors

None.
