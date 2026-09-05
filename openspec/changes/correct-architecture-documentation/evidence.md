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

## Pending

- Pull request against `main`: head, base branch, base SHA and required check
  run ids, recorded here once opened.
- Archival after integration.
