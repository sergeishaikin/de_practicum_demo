## Authorisation

Covered by the bounded Next Generation `ADOPT` programme recorded on 2026-08-19.
Third item of the programme, selected by re-reading the register and ADR-0003
after NG-0.1 archived: NG-0.2, Wave 2, `ADOPT`, hard dependency NG-0.1 satisfied.

## Why

NG-0.1 gave the platform a vocabulary for identity. Nothing yet emits the
*relationships* between the datasets those identifiers describe. The processing
graph — Kafka, a Spark streaming job, a landing prefix, three Iceberg tables,
Airflow, dbt — exists only as prose and as code someone has to read.

NG-0.2 makes the graph a runtime fact: each first-party boundary emits an
OpenLineage event naming the datasets it actually read and wrote, tagged with
the run identifiers that execution really had.

The protocol is chosen so the backend stays replaceable. NG-0.3 will introduce
OpenMetadata as the first UI; nothing here may make that a rewrite.

## What Changes

- **`iceberg/common/lineage.py`** — the naming contract and a fail-open emitter.
  Deterministic dataset names, an edge-ownership registry that refuses two
  producers for one edge, and an emitter that cannot break the data path.
- **`iceberg/writer/iceberg_writer.py`** — emits `landing → bronze.orders` with
  the real `load_id` and the snapshot the append produced.
- **`iceberg/medallion/iceberg_medallion.py`** — emits `bronze → silver` and
  `silver → gold` with the real `cycle_id` and snapshot ids.
- **`apache-airflow-providers-openlineage==2.20.0`** — the native provider, with
  file transport and a fixed namespace.
- **`docs/LINEAGE.md`** — the naming contract, the emitter rules, and the one
  edge this change does not close.
- Tests: naming determinism, the duplicate-edge negative test, a backend-down
  test proving processing is unaffected, captured-event assertions, and a live
  receipt read out of the running stack.

**Not in this change — the Spark listener, and why.** Verified against primary
sources on 2026-08-20: OpenLineage's Spark integration builds variants `spark3`
through `spark40`, and `gradle.properties` pins `spark40.spark.version=4.0.0`.
There is no `spark41` or `spark42` module. This repository runs Spark **4.2.0**.
The item's own scenario governs this case: the integration stays disabled, and
the blocker and the fallback path are documented rather than downgrading Spark.

The consequence is explicit: the `Kafka orders topic → streaming job → landing`
edge is **not** emitted. It is recorded as a named gap in `docs/LINEAGE.md`, not
inferred and not attributed to a job that did not perform it. Every other edge
in the item's acceptance graph is emitted from the boundary that actually
performs it.

**Scope fence:**

- No processing semantics change. Lineage emission is additive and fail-open:
  an emitter fault or an unavailable transport SHALL NOT alter what is written
  to Kafka, MinIO, Postgres or Iceberg.
- `spark/` is not modified. No Spark listener, agent or job change.
- No lineage backend or UI is deployed; that is NG-0.3.
- No table, schema, snapshot property or metric label changes.
- `git diff --exit-code spark/ dbt/ trino/ superset/ kafka/ .planning/` SHALL be
  clean.
- Coverage threshold unchanged; no test weakened.

## Capabilities

### Added Capabilities

- **`runtime-lineage`** — what may be claimed as a lineage edge, who owns an
  edge, and how a lineage failure is required to behave.

## Impact

- `iceberg/common/lineage.py`, `docs/LINEAGE.md` — new.
- `iceberg/writer/iceberg_writer.py`, `iceberg/medallion/iceberg_medallion.py` —
  emission at existing boundaries.
- `iceberg/requirements.in` / `.txt`, `airflow.requirements.in` / `.txt`,
  `pyproject.toml`, `uv.lock` — the OpenLineage client and the Airflow provider.
- `docker-compose.extended.yml`, `docker-compose.yml` — transport configuration
  and the shared lineage volume.
- `tests/test_lineage_contract.py`, `tests/integration/test_lineage_receipt.py` —
  new.
- `openspec/backlog/next-generation/00-INDEX.md` — NG-0.2's authorisation date.
