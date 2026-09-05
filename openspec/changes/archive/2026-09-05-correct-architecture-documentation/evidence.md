# Evidence: correct-architecture-documentation

## Preflight

`main` and `origin/main` at `ee60a49`; branch `docs/architecture-correctness`
cut from it, with `git merge-base --is-ancestor` confirmed before the first
edit.

## The asserted edge has no implementation

Searching all five files in `dags/` for Spark, port 15002 and connection calls
returns only `trino.dbapi.connect` and `psycopg2.connect`. No DAG imports
`pyspark`, uses an `sc://` URI, or names a Spark service. `spark-connect` is
declared `profiles: ["tools"]` at `docker-compose.extended.yml:102`.

## Shipped medallion defaults

| Source | SILVER_MODE | GOLD_SOURCE | SHADOW_COMPARE |
| --- | --- | --- | --- |
| `docker-compose.extended.yml:368-370` | `legacy` (default substitution) | `legacy` | `0` |
| `.env.example:113-115` | `legacy` | `legacy` | `0` |

Both agree. A stack started from the committed configuration runs the
full-rebuild `legacy` mode, so the sentence the brief called stale was
accurate. What was absent is that it describes one of four validated modes;
`RUNTIME_ROLLOUT_MATRIX` in `iceberg/common/cutover.py` holds all four, and
`validate_runtime_config()` raises on any combination outside it.

## Profile documentation, before and after

Declared across the Compose files: `bi`, `metadata`, `observability`,
`observability-next`, `otel`, `tools` — six.

| Tree | Documented in the README table |
| --- | --- |
| `origin/main` | `bi`, `metadata`, `observability`, `tools` — four |
| this branch | all six |

Run against the README on `origin/main`, the new check reports
`observability-next` and `otel` missing and fails. It is not passing vacuously.

## Cross-document sweep

After the edits, none of `README.md`, `AGENTS.md`, `CLAUDE.md`,
`docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md` or `docs/DEPLOYMENT.md` matches
any of the four corrected claims: an Airflow-to-Spark-Connect edge, "rebuilds
silver", "backed by MinIO", or "No explicit convention".

`docs/ARCHITECTURE.md` needed one sentence only. Its mermaid diagrams were
already plane-separated and already omitted the false edge; the README was the
stale document.

## Completion gate

| Check | Result |
| --- | --- |
| `uv run --locked ruff check .` | All checks passed |
| `uv run --locked black --check .` | 111 files unchanged |
| `uv run --locked mypy` | Success: no issues found in 10 source files |
| `uv run --locked pytest` | 624 passed, 1 skipped, 81 deselected |
| `pytest tests --cov=iceberg --cov-fail-under=90` | Required coverage reached, 92.62% |

## Merge-time authority

Pull request **#19**, `Rebuild the README architecture around the platform's
real planes`.

| | |
| --- | --- |
| Head | `docs/architecture-correctness` @ `c12954821e87e4a2ccddbb7e135bfdd392204f4b` |
| Base branch | `main` |
| Base SHA | `ee60a49fe4a5c739112ae4d6ff25ec26c7fa43b3` |
| Merge commit | `770a9018c93ad37304f5bc202809d5a612eda09f` |
| Merged | 2026-09-05T09:49:09Z, squash |
| Branch after merge | deleted automatically |

Workflow runs on that head, both `pull_request` events, base `main@ee60a49f`:

| Workflow | Run | Conclusion |
| --- | --- | --- |
| CI | `33958820725` | success |
| M5 architecture gates | `33958820689` | success |

Required check jobs: Lint + compose validation `101286932919`, Unit tests +
coverage `101286932916`, Warehouse dbt contract + artifacts `101286932855`,
Airflow DAG validation `101286932900`, PR M3/M4 recovery and cutover gates
`101286932614`. `mergeStateStatus=CLEAN` before merge.

## A recovery worth recording

The first attempt to open this pull request failed with `No commits between
main and docs/architecture-correctness`. The branch had been created in one
worktree while the edits were made in another, so the commit landed on the
previous change's branch and the pushed branch was empty.

Recovered by rebasing the commit `--onto origin/main`, freeing the branch name
from the worktree holding it, renaming, and pushing — `c129548`, one commit
ahead of `main`, ancestry re-verified. No work was lost and nothing was
force-pushed over.

This is the failure mode the **Closure includes branch and worktree cleanup**
requirement exists to reduce, encountered while carrying it out: several live
worktrees make "which branch am I on" a question that must be answered rather
than assumed.
