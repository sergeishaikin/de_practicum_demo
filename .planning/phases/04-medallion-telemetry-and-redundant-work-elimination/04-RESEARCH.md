# Phase 4: Medallion Telemetry and Redundant Work Elimination — Research

**Researched:** 2026-08-17
**Domain:** In-repo Python observability + PyIceberg snapshot provenance + idempotency receipts
**Confidence:** HIGH for everything answerable by source inspection; MEDIUM where a live stack would be needed and was deliberately not started.
**Method:** static source inspection only. No Docker command was invoked, no service started, no table mutated, no pipeline or dbt run. The only code executed was `python -c` against the already-installed host `.venv` to read PyIceberg signatures — no catalog, no network, no S3.

---

<user_constraints>
## User Constraints (from 04-CONTEXT.md)

### Locked Decisions

**P0 — Correct telemetry semantics**

- Introduce a stable `cycle_id` identifying one outer medallion cycle.
- Distinguish `phase` explicitly: `b2`, `shadow`, `gold`, `cycle`.
- Phase durations must be **non-overlapping, or documented as inclusive** — one or the other, decided and stated, never left implicit.
- Record enough state to explain a cycle: `bronze_snapshot_id`, `silver_snapshot_id`, `gold_snapshot_id` where meaningful, work/files/keys processed, and the shadow comparison result.
- Dashboards and queries must not be able to double-count nested B2 time.
- Add tests proving one logical run produces one cycle record plus correctly associated phase records.

**P0 — The historical interpretation rule (CORRECTED before planning)**

Six emission sites, not two:

| Site | Function | status | sets `gold_duration_ms`? |
|---|---|---|---|
| `iceberg_medallion.py:542` | `run_b2` | `failed` | no |
| `:602` | `run_b2` | `success` | no |
| `:979` | `_legacy_silver_cycle` | `failed` | no |
| `:1033` | `_run_legacy` | `success` | **yes** |
| `:1089` | `_run_m4` | `shadow_failed` | **no** |
| `:1109` | `_run_m4` | `success` | **yes** |

The corrected rule that must be documented and tested:

| `status` | `gold_duration_ms` | Classification |
|---|---|---|
| `success` | > 0 | outer cycle (`_run_m4` or `_run_legacy`) |
| `success` | 0 | nested B2 phase (`run_b2:602`) |
| `shadow_failed` | 0 | **outer cycle**, aborted before Gold |
| `failed` | 0 | nested phase; **no outer record exists** for that cycle |

Two consequences the plan must carry:

1. The naive rule misclassifies `shadow_failed` — the safety-critical row — as a nested B2 metric. Any documented rule must be status-qualified.
2. **Recorded evidence contains only `status: success` rows.** The `shadow_failed` and `failed` branches are derived from reading the code, not observed. The documentation must say so rather than implying all four branches were verified against data.

**P1 — Proven no-op shadow fast path**

- Do **not** skip on Bronze snapshot identity alone. Silver can move independently through recovery, and a Bronze-only check would skip validation that should run.
- Persist a shadow-comparison receipt containing at least: `bronze_snapshot_id`, `silver_snapshot_id`, runtime/cutover configuration identity, projection/business-contract version, comparison result, comparison timestamp.
- Skip the full Bronze scan, legacy rebuild and comparison **only when all hold**: current Bronze == certified Bronze; current Silver == certified Silver; runtime/projection contract unchanged; previous comparison succeeded.
- Any change to Bronze or Silver invalidates the fast path.
- When a comparison does run, preserve the existing pinned Bronze boundary (`_pin_bronze_boundary`) so the legacy candidate and the B2 result describe the same logical source.
- Recovery or independent Silver movement must force revalidation.

**P1 — Gold provenance / no-op rebuild**

- Record which persisted Silver snapshot produced the current Gold state, preferably as Iceberg snapshot metadata (`source-silver-snapshot-id`) or an equivalent durable receipt.
- If Silver has not changed and Gold is already certified from that exact Silver snapshot, do not rebuild or overwrite Gold.
- Any Silver change must rebuild Gold.
- Recovery must not let stale Gold provenance masquerade as current.
- Note: the writer already stamps `snapshot_properties={"load-id": ...}` and re-checks it against snapshot summaries during recovery. Gold provenance is the same in-repo idiom, not a new mechanism.

**P2 — Steady-state shadow policy**

- Analyse whether `SHADOW_COMPARE` must stay permanently enabled after a successful cutover.
- Do **not** simply add `(b2, persisted_silver, 0)` to `RUNTIME_ROLLOUT_MATRIX`.
- Define the evidence and safety conditions for moving from cutover validation to steady state. Candidate outcomes: permanent shadow, change-triggered shadow, sampled/periodic shadow, or shadow disabled after a certified cutover.
- Preserve rollback guarantees.

**P3 — Arrow/Python boundary, last**

- Measure delta sizes and time in: Arrow→Python conversion, `collapse_delta`, `resolve_against_current`, Python→Arrow reconstruction.
- Optimise **only if still measurable** once redundant full-state work is gone.
- Prefer an Arrow-native/vectorised implementation before any other language.
- FF-14 semantics must be preserved exactly: same `order_id` + same `business_version` + different business payload ⇒ **reject**. This is a conflict detector, not an aggregation, and is not a mechanical `group_by`.

### Claude's Discretion

- Plan/task decomposition and commit boundaries.
- Whether the shadow receipt lives in Postgres, as Iceberg snapshot properties, or in writer-style state — provided it is durable and survives restart.
- Metric schema mechanics (new columns vs a new table), provided historical rows stay interpretable.
- Test names and placement within the existing suite layout.

### Deferred Ideas (OUT OF SCOPE)

- Any Rust component, including the Bronze writer. Unmeasured, not rejected.
- Replacing Spark Structured Streaming.
- Full-volume Olist load and the re-measurement it would justify.
</user_constraints>

---

## Summary

Every locked decision in this phase is implementable with the libraries already pinned in `iceberg/requirements.txt`. **No new dependency is required, and none is recommended.** The single highest-risk unknown — whether PyIceberg 0.11.1 `Table.overwrite()` accepts `snapshot_properties` — resolves cleanly: it does, and the repository already relies on exactly that mechanism in production for B2 Silver recovery (`iceberg_medallion.py:562-571` writes `silver-work-id` via `overwrite`; `silver_committed_work_ids()` at `:307-315` reads it back out of snapshot summaries across process restarts). Gold provenance is therefore a one-line stamp plus a read, not a new mechanism.

The real risk in this phase is not the mechanism, it is the **blast radius of two behavioural changes into existing green contracts**. Two findings dominate the plan:

1. **`tests/support/medallion_harness.py:181-200` will hang and fail the moment the Gold no-op skip lands.** `wait_for_new_gold_snapshot` is documented as relying on the invariant "Every cycle ends in a Gold overwrite, so a new Gold snapshot is proof the deployment actually did work." GLD-01 deletes that invariant. This harness backs `gold_cutover.feature`, which `ci-m5-gates.yml` runs as a **PR-blocking** gate on every change under `iceberg/**`. A replacement liveness proof must land in the *same* wave as the Gold skip, not after it.
2. **`docs/adr/0001-incremental-silver-and-gold.md` D-4 (status: ✅ ACCEPTED) states verbatim: "Gold is not made incremental. It is rebuilt in full from persisted Silver on every cycle."** GLD-01 contradicts the literal wording. It does *not* contradict D-4's intent (Gold is still an exact full rebuild whenever it is built), but the ADR is a ratified contract document and must be amended with a superseding note in this phase, not silently violated.

On telemetry: the double-count is worse than `marts.lakehouse_metrics` alone suggests. Because `_RuntimeMetrics` labels every gauge by `source` only, and both the nested `run_b2` record and the outer `_run_m4` record use `source="medallion"`, the **outer record overwrites the nested record's gauges with zeros** — `lakehouse_files{source="medallion",kind="planned"}` and `lakehouse_bytes{...}` are reset to 0 immediately after every cycle that measured them. Meanwhile the counters (`lakehouse_events_total`) increment **twice per logical cycle** and the `lakehouse_duration_seconds` histogram observes both the nested and the enclosing duration. Fixing metric identity therefore has to fix the Prometheus label set too, not just the Postgres schema.

**Primary recommendation:** thread a `cycle_id` through `_run_m4`/`run_b2`/`_run_legacy`, add `cycle_id` + `phase` + the three snapshot-id columns additively to `marts.lakehouse_metrics` via the existing `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idiom, re-base the timers to make phase durations **non-overlapping** (cycle is the documented envelope), and put both the shadow receipt and the Gold provenance in **Iceberg snapshot properties on the tables they describe** — Gold provenance on the Gold snapshot, shadow certification as a Postgres receipt table. Sequence the Gold skip and the harness replacement in one wave.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `cycle_id` generation and phase attribution | Medallion application process (`iceberg/medallion/iceberg_medallion.py`) | — | Only the process that runs the cycle knows the cycle boundary. `common/ops.py` is a dumb sink and must stay one. |
| Durable metric row schema | PostgreSQL `marts` schema, DDL owned by `iceberg/common/ops.py` | — | Established: auto-DDL + additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (`ops.py:51-67`). |
| Live Prometheus label set | Medallion in-process `_RuntimeMetrics` (`ops.py:226-333`) | Prometheus rules/Grafana JSON under `observability/` | Gauge/counter cardinality is decided at `observe()` time; dashboards and alerts must be updated in lockstep or they read the wrong series. |
| Durable metric projection to Prometheus | `observability/postgres_exporter.py` | — | It is the only reader of the durable table for Prometheus and uses `distinct on (source)` — adding rows under the same `source` changes what "latest" means. |
| Gold source provenance | Iceberg Gold table snapshot summary | — | Provenance must travel with the artifact it describes and survive an arbitrary process restart. Same idiom as `load-id` / `silver-work-id`. |
| Shadow certification receipt | **MinIO object store, medallion-owned** (`MEDALLION_SHADOW_RECEIPT_PATH`) — *amended, see the note below this table* | ~~PostgreSQL `marts` (new table)~~ (superseded); Iceberg snapshot properties (rejected — see §3) | The receipt is about a *relationship between two tables plus runtime config*, so it belongs to neither table's snapshot history. This row originally assigned it to PostgreSQL on the `marts.maintenance_runs` / `marts.pipeline_runs` precedent; planning superseded that. |
| Rollout state machine validation | `iceberg/common/cutover.py` | — | Unchanged this phase. P2 is analysis only. |
| Integration-test liveness detection | `tests/support/medallion_harness.py` | `tests/features/test_gold_cutover.py` | Must stop using "a new Gold snapshot appeared" as the proof a cycle ran. |

> **Amendment (planning, 2026-08-18) — shadow certification receipt tier.** Recorded as a
> superseding amendment rather than a silent edit, in the same style as the ADR-0001 D-4
> amendment this phase makes.
>
> The row above originally read *PostgreSQL `marts` (new table)*, per §3d. Planning
> **resolved against that recommendation** and assigned the receipt to the medallion's own
> MinIO state, alongside `progress.json` and the completion ledger. Decided in
> `04-06-PLAN.md`; see Open Question 4 below for the full reasoning. In short:
> `.github/workflows/ci-m5-gates.yml:41` starts only `minio iceberg-rest`, and
> `tests/support/medallion_harness.py` sets `METRICS_ENABLED: "0"`, so a PostgreSQL receipt
> would make SHD-01h and the fast path unreachable in the only integration gate this
> repository has. The accepted cost is that the certificate itself is not SQL-queryable;
> the *decision* it drives (`shadow_skipped`, `shadow_comparisons`) is still recorded on
> the metric rows in PostgreSQL.
>
> §3b option A and §3d are historical as written and are superseded by this row.

---

## Research Question 1 — Gold provenance feasibility

### 1a. Does PyIceberg 0.11.1 `Table.overwrite()` accept `snapshot_properties`?

**VERIFIED — YES.** Four independent lines of evidence:

**Evidence A — runtime signature inspection against the pinned version.**
```
$ ./.venv/Scripts/python.exe -c "import inspect, pyiceberg; from pyiceberg.table import Table, Transaction; ..."
pyiceberg 0.11.1
Table.overwrite (self, df: 'pa.Table', overwrite_filter: 'BooleanExpression | str' = AlwaysTrue(), snapshot_properties: 'dict[str, str]' = {}, case_sensitive: 'bool' = True, branch: 'str | None' = 'main') -> 'None'
Table.append   (self, df: 'pa.Table', snapshot_properties: 'dict[str, str]' = {}, branch: 'str | None' = 'main') -> 'None'
Txn.overwrite  (self, df: 'pa.Table', overwrite_filter: 'BooleanExpression | str' = AlwaysTrue(), snapshot_properties: 'dict[str, str]' = {}, case_sensitive: 'bool' = True, branch: 'str | None' = 'main') -> 'None'
```
The pinned version is the one the iceberg image installs: `iceberg/requirements.in:1` — `pyiceberg[pyarrow]==0.11.1`; the same version is present in the host `.venv` (`.venv/Lib/site-packages/pyiceberg-0.11.1.dist-info/`) and in `pyproject.toml:14`.

**Evidence B — source path from `overwrite` to the snapshot summary.**
- `.venv/Lib/site-packages/pyiceberg/table/__init__.py:1443-1475` — `Table.overwrite` forwards `snapshot_properties` into `Transaction.overwrite`.
- `:594-653` — `Transaction.overwrite` passes `snapshot_properties` to **both** the internal `self.delete(...)` (`:639-644`) and `self._append_snapshot_producer(snapshot_properties, ...)` (`:646`).
- `.venv/.../pyiceberg/table/update/snapshot.py:281` — `summary = self._summary(self.snapshot_properties)`.
- `:273` — `Summary(operation=self._operation, **ssc.build(), **snapshot_properties)` — the custom keys are merged directly into the summary.
- `.venv/.../pyiceberg/table/snapshots.py:346-386` — `update_snapshot_summaries` only recomputes `total-*` counters; it does **not** filter unknown keys.

**Evidence C — the repository already does this in production, on `overwrite`, not just `append`.**
`iceberg/medallion/iceberg_medallion.py:562-571`:
```python
silver.overwrite(
    _rows_to_silver(resolved),
    overwrite_filter=In("order_id", sorted({row["order_id"] for row in resolved})),
    snapshot_properties={
        SILVER_WORK_ID_KEY: load_id,
        "changed-keys": str(len(resolved)),
    },
)
```
and it reads the value back out of snapshot history at `:307-315`:
```python
def silver_committed_work_ids(silver) -> dict[str, int]:
    for snapshot in silver.metadata.snapshots:
        work_id = snapshot.summary.additional_properties.get(SILVER_WORK_ID_KEY)
```
That read is the crash-after-commit recovery path (`:502-512`). It runs in a **freshly started process** with no memory of the write. This is the exact durability property Gold provenance needs.

**Evidence D — a live run already produced it.** `artifacts/b2-rollout/06-bounded-workload.json` records, from a real cutover-stage run on 2026-08-10:
```json
"silver_work_id": "288d37c3810c4f97b6072768098e5d01",
"silver_snapshot_id": 3206326457309031755
```
An overwrite-written custom snapshot property was read back from a live REST catalog and recorded as evidence.

**Conclusion:** `snapshot_properties` on `overwrite` is not a risk. `_write_gold` (`iceberg_medallion.py:1006-1014`) currently passes none; adding `snapshot_properties={"source-silver-snapshot-id": str(sid)}` is a one-line change on an already-proven mechanism.

**UNVERIFIED (and why):** I could not execute an end-to-end write/read round-trip offline. `pyiceberg.catalog.sql.SqlCatalog` and `pyiceberg.catalog.memory.InMemoryCatalog` both `import sqlalchemy`, which is not installed in the host `.venv` (`ModuleNotFoundError: No module named 'sqlalchemy'`), and the only other catalogs available (`rest`, `glue`, `hive`, `dynamodb`, `bigquery_metastore`, `noop`) need a live service. Starting the REST catalog is forbidden by the read-only rule. Evidence C and D make this gap immaterial.

### 1b. Behavioural details of `overwrite` the plan must account for

| Finding | Evidence | Consequence for planning |
|---|---|---|
| A full `overwrite` (`overwrite_filter=ALWAYS_TRUE`, the default used by `_write_gold`) produces up to **two** snapshots: a DELETE then an APPEND. Both carry the same `snapshot_properties`. | `pyiceberg/table/__init__.py:637-653` | Reading provenance from `current_snapshot()` is correct — the APPEND is last and carries the property. But `len(metadata.snapshots)` grows by 2 per Gold write, which is why the maintenance DAG has Gold in `MAINTENANCE_TABLES` (`dags/lakehouse_maintenance.py:32-36`). |
| The DELETE half is elided when nothing matches: `_DeleteFiles._commit` returns `(), ()` when `not self.files_affected`. | `pyiceberg/table/update/snapshot.py:396-401` | A first-ever Gold write produces 1 snapshot; subsequent ones produce 2. Any test counting Gold snapshots must not assume a fixed stride. |
| The APPEND half is **not** elided when the frame is empty — `_FastAppendFiles` does not override `_commit`. | `snapshot.py:521-547` (no `_commit` override) vs `:396-401` | A "stamp-only" empty overwrite would still create a snapshot. **Do not** use an empty overwrite to refresh provenance; it defeats the purpose of skipping the write. |
| Trino maintenance (`optimize`, `expire_snapshots`) creates Gold snapshots that carry **no** `source-silver-snapshot-id`. | `dags/lakehouse_maintenance.py:32-36` lists `("gold", "orders_daily_metrics")`; the procedures are Trino-side and know nothing about the property. | This is **fail-safe**, and should be stated as a deliberate property: after maintenance rewrites Gold, provenance reads as absent → the medallion rebuilds Gold once. Cost is one extra rebuild after a maintenance run; the alternative (walking snapshot history for the most recent property-bearing snapshot) would be **fail-open**, because an expired or superseded snapshot could vouch for a Gold state that maintenance has since rewritten. **Recommendation: read provenance from `current_snapshot()` only.** That satisfies "recovery must not let stale Gold provenance masquerade as current" by construction. |

### 1c. What the writer's recovery re-check pattern suggests

The writer's pattern (`iceberg/writer/iceberg_writer.py:386-419`, `:350-377`) is:

1. Write local intent first (`pending[load_id] = paths; save_state(...)`, `:441-442`).
2. Commit with the identity stamped into the snapshot (`table.append(..., snapshot_properties={LOAD_ID_KEY: load_id})`, `:458-461`).
3. On restart, re-derive truth **from the table**, not from local state: `committed_load_records(catalog)` scans `table.metadata.snapshots` for the stamp and reconciles (`:394-418`).

The transferable principle: **the catalog is the authority; local/derived state is a hint that must be re-validated against the catalog.** Applied to Gold, that means the skip decision must be `current_gold_snapshot.summary["source-silver-snapshot-id"] == str(current_silver_snapshot_id)` evaluated fresh each cycle from the catalog — never from an in-process cache, never from a sidecar file that could disagree with the table.

Note the medallion's own equivalent already exists and is *stronger*: `_mark_b2_completed` (`:328-365`) writes an immutable per-manifest receipt object to MinIO **before** updating progress, and `load_completion_ledger` (`:223-242`) refuses ambiguous receipts. That is the in-repo precedent for a receipt whose identity must be unforgeable.

---

## Research Question 2 — Who consumes `marts.lakehouse_metrics` today?

Complete enumeration (searched the whole repo, excluding `.git`/`.venv`/`__pycache__`).

### 2a. Machine consumers (break if semantics change)

| # | Consumer | Location | Reads | Breaks if `cycle_id`/`phase` are **added**? | Breaks if existing column semantics **change**? |
|---|---|---|---|---|---|
| C1 | **Prometheus durable exporter** | `observability/postgres_exporter.py:46-62` | `select distinct on (source) source, status, extract(epoch from metric_ts), duration_ms ... order by source, metric_ts desc` | **No** — additive columns are ignored. **But it silently changes meaning**: `distinct on (source)` returns whichever medallion row was written *last*. Today that is the outer `_run_m4` record (nested `run_b2` emits first — verified by the timestamp ordering in `06-o1-window.json`). If the plan emits phase rows *after* the cycle row, `lakehouse_source_last_duration_seconds{source="medallion"}` starts reporting a **phase** duration instead of the cycle duration. | **Yes** for `status`: `SOURCE_UP` is `1 if status in {"success","ok","noop"} else 0` (`:58-60`). Introducing a new status such as `skipped` or `noop_cycle` for a fast-path cycle would flip the gauge to 0 unless that literal set is extended. |
| C2 | **In-process Prometheus runtime metrics** | `iceberg/common/ops.py:133-154` → `_RuntimeMetrics.observe` `:304-332` | Every `Metrics.record()` call, labelled by `source` only | **Not by the columns themselves** — but this is the *worst* existing defect and the plan must fix it here. See §2c. | **Yes.** Any change to what `record()` is called with changes the live gauges immediately. |
| C3 | **Grafana dashboard** | `observability/grafana/dashboards/lakehouse-runtime.json` — 8 targets, all keyed on `source` (and `status`/`state`/`kind`/`stage`) | See §2c table | Only if new Prometheus label values appear (e.g. a `phase` label or new `source` values) — panel legends would gain series. | **Yes** for `lakehouse_duration_seconds` / `lakehouse_stage_duration_seconds` panels. |
| C4 | **Prometheus alert rules** | `observability/prometheus/alerts.yml` | `LakehouseUnresolvedWork` keys on `lakehouse_work{state="in_flight"}` **and** `lakehouse_source_last_event_timestamp_seconds{source="medallion"}`; `LakehouseApplicationFailure` on `increase(lakehouse_events_total{status="failed"}[10m]) > 0` | **Indirectly yes.** `lakehouse_events_total{status="failed"}` currently fires only from `run_b2:542` and `_legacy_silver_cycle:979`. If a phase row is ever emitted with `status="failed"` for a *non-fatal* phase, the alert fires spuriously. Any new status literal must be checked against this rule. | Yes. |
| C5 | **Deterministic E2E test** | `tests/e2e/test_lakehouse_e2e.py:511-945` | `_metrics_match` filters medallion rows by `bronze_rows`/`silver_rows`/`duplicates_removed`/`quality_violations` and asserts `any(status == "success")` (`:924-945`); `_canonical_leak_counts` counts rows in the canonical `dwh` DB (`:867-892`); `:512` truncates the table pre-run | **No.** Additive columns are ignored and the filter is value-based, so extra phase rows simply do not match. | **Yes** if the *legacy* path's row loses `bronze_rows`/`silver_rows`/`duplicates_removed`/`quality_violations`. The E2E runs the medallion with no `SILVER_MODE` → `legacy` → `_run_legacy` (`:1140-1141`) → the single `:1033` record. That row's four filter columns must keep their current meaning. |
| C6 | **Unit test on the insert statement** | `tests/test_ops.py:116-143, 182-202` | Asserts the literal `"insert into marts.lakehouse_metrics"` is present, and asserts on **positional parameter tuples**: `log[1][1][:11] == (...)` and `log[1][1][11:] == (0,) * 17`; `log[1][1][11:21] == (2,0,4,3,1,0,1,0,11,7)` | **Yes — guaranteed failure.** These assertions are positional and length-sensitive. Adding any column to the `insert` changes the tuple length and shifts every index. These two tests must be updated in the same commit as the DDL. This is the single most predictable test break in the phase. | Yes. |
| C7 | **`Metrics.record` signature** | `iceberg/common/ops.py:101-132` | 29 keyword-only params, all defaulted | Additive keyword params are safe for all callers. | — |
| C8 | **M5 cutover evidence path** | `scripts/verify_m5_cutover.py:1-39`, `iceberg/common/cutover.py:58-82` | Consumes a **hand-built JSON evidence file**, not the table. Docstring says the file "can be produced by ... an operations job after querying `marts.lakehouse_metrics`." | **No** — no live coupling. | No. |
| C9 | **Phase-1 plan verification commands** | `.planning/phases/01-b2-controlled-rollout/01-02-PLAN.md:80,108`, `01-05-PLAN.md:83`, `01-06-PLAN.md:123` | `select count(*) ... where source='medallion' and status='success' and shadow_comparisons > 0 ...`; `select source,status,sum(work_in_flight),sum(ff14_conflicts),sum(shadow_comparisons),sum(shadow_mismatches) ... group by source,status` | Historical plan artifacts, already executed. **Not re-run.** They are evidence, not a live gate. But note: `count(*) where status='success'` over an un-phase-filtered table is exactly the query class the phase must make impossible to write accidentally. | n/a (historical) |

### 2b. Human/documentation consumers (must be updated, will not "break" mechanically)

| Doc | Location | What it claims |
|---|---|---|
| `README.md:229-258` | "Every writer batch and medallion cycle inserts **one** row into `marts.lakehouse_metrics`" + a column table + a sample `group by source, status` query. | Both the "one row per cycle" claim and the sample query become misleading the moment phase rows exist. **Must be rewritten**, including the interpretation rule (TEL-02). |
| `CLAUDE.md:151` | "`Metrics.record()` writes **one** best-effort row per writer batch / medallion cycle" | Same claim; must be corrected. |
| `docs/ARCHITECTURE.md:21, 53, 72` | Mermaid edge `WRITER -->|metrics| PG`; "Every writer batch and medallion cycle writes one observability row" | Same claim. |
| `docs/DEVELOPMENT.md:136` | "writes one row to `marts.lakehouse_metrics` after each writer batch and each medallion cycle" | Same claim. |
| `docs/TESTING.md:15, 196` | Describes the table as the verification surface; gives `select source, status, count(*) ... group by 1,2` | Sample query becomes double-counting. |
| `docs/observability/O1-runtime-observability.md:16, 31, 62-66` | Ownership table + the **metric contract** list (`lakehouse_events_total`, `lakehouse_work`, `lakehouse_correctness_total`, `lakehouse_stage_duration_seconds`, `lakehouse_processed`, `lakehouse_files`, `lakehouse_bytes`) | If the Prometheus label set changes (§2c), this contract list is the document of record and must change with it. |
| `docs/remediation/M5-fitness-functions-and-cutover-gates.md:32-66` | "marts.lakehouse_metrics remains the operational sink. Its schema is extended **additively** and existing deployments are upgraded with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`." Plus two sample queries. | **This is the governing precedent for how to extend the schema.** Follow it exactly. |
| `docs/CONFIGURATION.md:74, 76` | Medallion env vars — note it currently omits `SILVER_MODE`, `GOLD_SOURCE`, `SHADOW_COMPARE`, `BRONZE_OUTBOX_PREFIX`, `MEDALLION_PROGRESS_PATH`, `MAX_COMPLETED_PROGRESS`. | Any new env var (e.g. a receipt path or a shadow-policy knob) must be added here, and the existing gap is worth closing opportunistically. |
| `.planning/quick/260816-docker-storage-investigation/260816-dsi-FINDINGS.md:141-145` | `lakehouse_metrics` = 8,804 rows, "grows ~970 rows/day and is the only real retention" concern. | Adding 3-4 phase rows per cycle **multiplies row growth by ~2-4×** at a 60 s interval. Flag as a known consequence; a retention decision is not in this phase's scope but the growth number should be restated honestly in the docs. |

### 2c. The Prometheus double-count is worse than the Postgres one — and is the actual "dashboards must not double-count" target

`_RuntimeMetrics.observe` (`ops.py:304-332`) labels **everything** by `source` alone. Both medallion `record()` calls per cycle pass `source="medallion"`. Consequences, all VERIFIED by reading `ops.py:304-332` against the two call sites (`:602-624` and `:1109-1126`) and cross-checked against `tests/test_ops.py:365-401` which explicitly documents "counters accumulate while gauges hold the latest cycle":

| Metric | Type | Today's behaviour per **one logical cycle** |
|---|---|---|
| `lakehouse_events_total{source="medallion",status="success"}` | Counter, `.inc()` | **Incremented twice.** One logical cycle looks like two events. |
| `lakehouse_duration_seconds{source="medallion"}` | Histogram, `.observe()` | **Two observations**: the nested B2 duration *and* the enclosing cycle duration, which contains it. `_sum` double-counts nested time; `_count` double-counts cycles. This is the headline defect. |
| `lakehouse_correctness_total{source="medallion",kind=...}` | Counter, `.inc()` | Incremented from both records. `ff14_conflicts` is only ever non-zero on the B2 record; the outer adds 0, so totals stay correct — but `lower_versions_ignored` is likewise B2-only and `shadow_mismatches` is outer-only, so the *totals* happen to survive by luck, not design. |
| `lakehouse_files{source="medallion",kind="planned"}` | Gauge, `.set()` | **Reset to 0** by the outer record. `_run_m4:1109-1126` passes no `files_planned`/`bytes_planned`/`files_removed`/`files_added`/`bytes_removed`/`bytes_added`, so the defaults (0) overwrite the real B2 values a few seconds later. The Grafana "Processed work and file amplification" panel therefore shows 0 almost always. |
| `lakehouse_bytes{source="medallion",kind=...}` | Gauge, `.set()` | Same — reset to 0. |
| `lakehouse_processed{source="medallion",kind="keys"}` | Gauge, `.set()` | Same — `keys_processed` reset to 0 by the outer record. |
| `lakehouse_work{source="medallion",state=...}` | Gauge, `.set()` | Same — `work_available`/`work_in_flight`/`work_completed` are B2-only and are reset to 0 by the outer record. **This directly weakens the `LakehouseUnresolvedWork` alert**, whose left-hand side is `lakehouse_work{state="in_flight"} > 0`. |
| `lakehouse_stage_duration_seconds{source="medallion",stage="silver"}` | Gauge, `.set()` | Last writer wins → the outer's *inclusive* silver duration. Arguably the intended value, but it is inclusive of B2. |

This is empirically consistent with the baseline artifact: `06-o1-window.json` rows alternate between a B2 row carrying the real physical-cost values and an outer row carrying zeros in those same columns.

**Planning consequence:** whatever `phase` distinction is introduced in Postgres must have a Prometheus counterpart, otherwise the "dashboards cannot double-count" requirement is unmet. Two options:

- **Add a `phase` label to the runtime collectors.** Cleanest semantically. Cost: every Grafana target and every alert expression gains a `phase` selector, `docs/observability/O1-runtime-observability.md` §Metric contract changes, and `tests/test_ops.py` `published(...)` helper calls all need the new label. Cardinality is bounded (4 phase values × 2 sources).
- **Emit the runtime observation only for the `cycle` phase**, keeping phase rows Postgres-only. Cheapest, no dashboard change, immediately removes the double-count and the gauge-reset defect — but loses live per-phase visibility, and requires the `cycle` record to carry the union of B2's physical-cost fields so the gauges stop reading 0.

Both are defensible. The second is strictly less work and fixes more existing defects; the first is more faithful to the locked "distinguish `phase` explicitly" wording. **Recommendation: option 2 plus roll-up** — `Metrics.record()` gains a `phase` kwarg; `_RuntimeMetrics.observe` is called only when `phase == "cycle"`, and the cycle record carries the roll-up of the B2 physical-cost fields. State this explicitly in `docs/observability/O1-runtime-observability.md` so the exclusion is a documented contract, not an omission. This also leaves C1's `distinct on (source)` correct **provided the cycle row is written last** — which the plan must assert with a test.

---

## Research Question 3 — Where can the shadow receipt durably live?

### 3a. Claim check: "the medallion currently has no durable state of its own"

**This claim is FALSE as stated, and the plan must not be built on it.**

The medallion owns **two** durable state artifacts, both in MinIO/S3, both written through `pyarrow.fs.S3FileSystem`:

| Artifact | Path (default) | Code | Nature |
|---|---|---|---|
| Progress ledger | `s3://de-practicum/streaming/medallion/progress.json` | `MEDALLION_PROGRESS_PATH` (`iceberg_medallion.py:59-61`); `load_progress` `:195-204`; `save_progress` `:207-210` | Mutable; `{version, next_sequence, work{}, completed{}}`; bounded to `MAX_COMPLETED_PROGRESS=100` entries by `_prune_completed` `:318-325`. |
| Completion ledger | `s3://de-practicum/streaming/medallion/completion-ledger/<load_id>.json` | `MEDALLION_COMPLETION_LEDGER_PREFIX` (`:62-65`); `load_completion_ledger` `:223-242`; `_append_completion_receipt` `:245-288` | **Immutable, one object per load-id, ambiguity is a hard error** (`:239-240`, `:264-269`). This is the closest existing analogue to a shadow receipt. |

What is true is narrower: **the medallion has no local-filesystem durable state and no Docker named volume.** `docker-compose.extended.yml` mounts only `./iceberg:/app:ro` for `iceberg-medallion` — compare `iceberg-writer`, which additionally mounts `de_demo_iceberg_writer_state:/state`. Adding a `/state` volume to the medallion would be a **compose/runtime configuration change**, pulling in `docker compose ... config --quiet` validation (AGENTS.md verification contract) and a `docs/DEPLOYMENT.md` / `docs/CONFIGURATION.md` update.

Also worth flagging: `MEDALLION_COMPLETION_LEDGER_PREFIX` is **not** declared in `docker-compose.extended.yml` and not in `.env.example` — the running service uses the code default. Any new receipt path env var should be declared explicitly rather than repeating that gap.

### 3b. Option comparison

| Option | Survives container restart | Survives `docker compose down` (no `--volumes`) | Survives `stack.ps1 reset` | Matches existing idiom | Verdict |
|---|---|---|---|---|---|
| **A. Postgres table** (e.g. `marts.shadow_certifications`) | ✅ | ✅ (`de_demo_postgres_data` volume) | ❌ — `scripts/stack-reset.ps1:13` runs `docker compose down --volumes --remove-orphans`, removing every named volume | ✅✅ Strong: `marts.maintenance_runs` (`dags/lakehouse_maintenance.py:67-77`, upsert with `on conflict (run_id, table_name) do update`) and `marts.pipeline_runs` (`dags/warehouse_orders.py:159`, additive migration precedent in ORCH-05). Auto-DDL from application code is already the norm (`ops.py:19-68`). | **Recommended for the shadow receipt.** |
| **B. Iceberg snapshot properties** | ✅ | ✅ | ❌ (`de_demo_minio_data` + `de_demo_iceberg_catalog` both removed) | ✅✅ Strongest of all — `load-id` on Bronze append (`iceberg_writer.py:460`), `silver-work-id` on Silver overwrite (`iceberg_medallion.py:568`) | **Recommended for Gold provenance.** Poor fit for the shadow receipt — see §3c. |
| **C. Writer-style JSON on a volume** (`/state/...`) | ✅ | ✅ | ❌ | ⚠️ Partial. The idiom exists (`iceberg_writer.py:106-124`, atomic temp-file + `os.fsync` + `os.replace`) but the medallion has **no volume**, so this requires a compose change. | Not recommended — highest incidental cost, no compensating benefit. |
| **D. MinIO object, medallion-style** (extend the completion-ledger pattern) | ✅ | ✅ | ❌ | ✅✅ Direct precedent — `_append_completion_receipt` `:245-288` | **Viable runner-up.** Reuses `FakeFS` from `tests/support/b2_fakes.py:63-84` for free, so unit tests are already tooled. Downside: the receipt contains a Postgres-shaped operational fact (config identity, comparison outcome) and MinIO has no query surface for an operator. |

**Note on "survives a stack reset": nothing does, and nothing should.** A reset destroys Bronze, Silver, Gold and the catalog. A shadow receipt that outlived them would certify a lake that no longer exists — that would be a *bug*, not a feature. Every option failing this row identically is the correct behaviour. State this explicitly rather than treating it as a differentiator.

### 3c. Why the shadow receipt does not belong in snapshot properties

The receipt's identity is a **tuple across three independent things**: `(bronze_snapshot_id, silver_snapshot_id, runtime/projection contract hash)`. Snapshot properties attach to a *single* table's single commit:

- Attaching it to Silver would mean writing a Silver snapshot purely to record a validation outcome — which **rewrites persisted Silver**, directly violating the contract asserted at `tests/features/test_shadow_cutover.py:240-242` (`silver.overwrite_calls == 0`) and `tests/features/test_gold_cutover.py:167-175` (snapshot identity, not just row equality).
- Attaching it to Bronze would have the medallion writing to Bronze, which it never does.
- Attaching it to Gold conflates two different receipts and breaks the moment the fast path skips Gold too.

Gold provenance is different: it is genuinely a property *of the Gold commit* (`this Gold state was built from that Silver snapshot`), which is exactly what snapshot properties are for.

### 3d. Concrete recommendation

**Two receipts, two homes:**

1. **Gold provenance → Gold snapshot summary.** `_write_gold` stamps `{"source-silver-snapshot-id": str(silver_snapshot_id)}`. The skip check reads `gold.current_snapshot().summary.additional_properties.get("source-silver-snapshot-id")` and compares to `_snapshot_id(silver)` (the helper already exists at `:931-938` and already tolerates test doubles without `current_snapshot`). Absent property ⇒ rebuild (fail-safe). Current-snapshot-only read ⇒ maintenance rewrites invalidate provenance automatically.

2. **Shadow certification → new Postgres table** in `marts`, auto-DDL'd from `iceberg/common/ops.py` alongside `METRICS_DDL`, single-row-per-certification with an upsert, following `marts.maintenance_runs` shape:

   | Column | Purpose |
   |---|---|
   | `certified_at timestamptz` | comparison timestamp (locked requirement) |
   | `bronze_snapshot_id bigint` | certified Bronze (locked) |
   | `silver_snapshot_id bigint` | certified Silver (locked) |
   | `runtime_identity text` | hash/canonical form of `(SILVER_MODE, GOLD_SOURCE, SHADOW_COMPARE)` (locked) |
   | `projection_version text` | business-contract version (locked) |
   | `result text` | comparison outcome (locked) |
   | `compared_keys bigint` | already produced by `compare_business_state` `:900` |
   | `cycle_id text` | ties the receipt to the metric rows |

   **Fail-closed rules the plan must encode:** a `NULL` Bronze or Silver snapshot id must never match (`_snapshot_id` returns `None` for a table with no snapshots, `:931-938`); a missing receipt means "run the comparison"; a Postgres outage means "run the comparison". Note that `Metrics.record` swallows all exceptions (`ops.py:210-215`) so that metrics can never break ingestion — the receipt **must not** inherit that behaviour in the *read* direction. A failed receipt read must degrade to running the full comparison, never to skipping it. Write-side may stay best-effort (a lost receipt costs one redundant comparison).

   **Projection version:** derive it from something that actually changes when the projection changes — e.g. a module-level `SHADOW_CONTRACT_VERSION` constant bumped by hand, plus a hash of `SHADOW_BUSINESS_COLUMNS + SHADOW_EXCLUDED_COLUMNS` (`iceberg_medallion.py:780-793`). A hand-bumped constant alone is a silent-staleness hazard; the column-tuple hash catches the most likely real change automatically.

---

## Research Question 4 — Established test idioms

### 4a. How `Metrics.record` is faked or captured today

**One canonical double, duplicated once.**

| Idiom | Location | Shape |
|---|---|---|
| Shared `FakeMetrics` | `tests/support/fakes.py:90-95` | `class FakeMetrics: self.records: list[dict]; def record(self, **kwargs): self.records.append(kwargs)` — captures the **kwargs dict**, not a formatted row. |
| Local duplicate | `tests/test_m4_gold.py:99-104` | Byte-identical re-declaration. Pre-existing duplication; the plan may consolidate but is not required to. |
| Assertion style | `tests/test_b2_medallion.py:135-145`; `tests/test_m4_gold.py:158-171`; `tests/test_medallion.py:264-270, 301-302, 331-332`; `tests/features/test_shadow_cutover.py:245-270` | Always `metrics.records[-1]["<kwarg>"] == expected`. **`records[-1]` is used everywhere.** |

**This is the most important test-idiom finding.** `records[-1]` is precisely the assertion style that a phase-record change invalidates: once one logical run emits several records, "the last one" is ambiguous. Every `records[-1]` site above must be re-examined. The natural replacement idiom, consistent with the locked requirement "one cycle record plus correctly associated phase records", is a helper on `FakeMetrics`:

```python
def phase(self, name: str) -> dict:      # exactly one record with phase == name
def cycle(self) -> dict:                 # the single phase == "cycle" record
```
returning the record and asserting uniqueness. Placing it on the shared `tests/support/fakes.py:90` double makes it available to unit and BDD layers at once. Note `tests/test_m4_gold.py` uses its own copy — either consolidate or update both.

### 4b. Prometheus-side assertion idiom

`tests/test_ops.py:32-44` defines `published(collector, name, **labels)`, which walks `collector.collect()` and returns the sample value for an exact label set, raising if absent. Its docstring states the intent: "Asserting on collected samples rather than on call counts proves the value an operator's dashboard would actually see, including the label set it is filed under."

Consequences:
- If a `phase` label is added, **every** `published(...)` call in `tests/test_ops.py:281-455` gains a `phase=` kwarg or fails with `AssertionError: no sample ...`. That is ~20 call sites.
- The port-binding is faked, not bound: `served` fixture at `:233-243` monkeypatches `prometheus_client.start_http_server`. New collectors need no new infrastructure.
- `test_counters_accumulate_while_gauges_hold_the_latest_cycle` (`:365-401`) is the test that documents the gauge-overwrite semantics. If option 2 from §2c is chosen (observe only on the cycle phase), this test's premise stays valid but a new test should prove that a nested phase record does **not** reach the runtime collectors.

### 4c. Catalog/table doubles

Three distinct doubles exist deliberately — a comment at `tests/support/b2_fakes.py:9-12` explains why they must not be merged ("a single conflated double would have to accept either signature and would stop proving which path ran").

| Double | Location | Models | Has `current_snapshot()`? | Records `snapshot_properties`? |
|---|---|---|---|---|
| `tests/support/fakes.py` `FakeTable` | `:29-69` | Legacy medallion slice: unfiltered `overwrite(df, **kwargs)` | ✅ `:58-59` | ✅ `:67-69` — appends to `self.snapshot_properties` **and** seeds a snapshot summary. |
| `tests/support/b2_fakes.py` `FakeIcebergTable` | `:112-161` | B2 slice: `overwrite(arrow_table, overwrite_filter, snapshot_properties=None)`, plus `plan_files()` cost and realistic `deleted-data-files`/`added-files-size` summaries | ✅ `:160-161` | ✅ `:150-158` |
| `tests/test_m4_gold.py` local `FakeTable` | `:76-89` | Minimal: `overwrite(arrow_table, **kwargs)`, counts calls | ❌ **No `current_snapshot`** — `_snapshot_id` (`:931-938`) falls back to `metadata.current_snapshot_id`, and `metadata` is also absent, so `getattr(None, ...)` → `_snapshot_id` returns `None`. | ❌ discards them |

**Planning consequence:** `tests/support/fakes.py:FakeTable` already records snapshot properties and exposes `current_snapshot()`, so Gold-provenance unit tests can be written against it with **zero double changes** — the double was built for exactly this ("A one-shot migration has to be auditable after the fact, so 'which snapshot did this write produce, and what provenance did it record' is part of the contract", `:38-41`). The `test_m4_gold.py` local double will need `current_snapshot()`/snapshot-property capture added, or should be replaced by the shared one.

### 4d. BDD layer idioms

| Feature | Marker | Runs in | Step-file idiom |
|---|---|---|---|
| `shadow_cutover.feature` | `@bdd @domain`, `pytestmark = [pytest.mark.bdd]` (`test_shadow_cutover.py:34`) | **default fast suite** | Pure domain, in-memory doubles. Binds to production callables `validate_runtime_config` and `run` (`:105`). Stages are a module-level `STAGES` dict (`:46-55`); `_stage()` monkeypatches `m.GOLD_SOURCE`/`m.SHADOW_COMPARE_ENABLED` (`:94-99`); `run_b2` is stubbed to a no-op (`:90`). Assertions go through `context["metrics"].records[-1]` (`:245-270`). |
| `gold_cutover.feature` | `@bdd @integration`, `pytestmark = [bdd, integration]` (`test_gold_cutover.py:36`) | `ci-m5-gates.yml` (PR-blocking on `iceberg/**`), `ci-integration.yml`, `ci-nightly.yml` | Live REST catalog + MinIO via `tests/support/medallion_harness.py`; per-run isolated namespace (`h.isolated_lake()`); each stage is a **separate subprocess deployment** (`h.start_medallion`, `:102-141`). |
| `silver_business_state.feature` | `pytestmark = [bdd]` (`test_silver_business_state.py:23`) | default fast suite | Business-state contract; not expected to change. |
| `writer_crash_recovery.feature` | `[bdd, integration]` | m5 gates | Writer-side; unaffected. |
| `retention_recovery.feature`, `legacy_cleanup_safety.feature`, `data_quality_modes.feature` | `[bdd]` | default fast suite | Unaffected. |

The step files carry an explicit **scope-boundary docstring** stating what belongs in the feature and what stays in unit tests (`test_shadow_cutover.py:3-18`, `test_gold_cutover.py:3-23`). New scenarios must carry the same justification, and the split must be respected: *what a comparison decides* stays in `test_m4_gold.py`; *what the system does when a receipt is valid* is a system rule and belongs in a feature.

### 4e. ⚠️ The blocking test finding

`tests/support/medallion_harness.py:181-200`:

```python
def wait_for_new_gold_snapshot(cat, namespace, previous, timeout=90):
    """Wait until this deployment has completed at least one full cycle.

    Every cycle ends in a Gold overwrite, so a new Gold snapshot is proof the
    deployment actually did work. Waiting on a row count instead would return
    immediately whenever the previous stage already produced those rows, and the
    deployment would be stopped before running at all.
    """
```

and `run_deployment` (`:203-230`) calls it unconditionally on every stage.

`test_gold_cutover.py` walks three deployments — `shadow` (`:112-115`), `cutover` (`:117-121`), `shadow` again (`:123-128`) — over a lake whose Silver does **not** change between stages (that is the entire point of the scenario: `silver_untouched` asserts `snapshots == before_snapshots`, `:167-175`). Under GLD-01, deployments 2 and 3 skip the Gold write, no new Gold snapshot appears, and `wait_for_new_gold_snapshot` raises `AssertionError: ... gained no snapshot within 90s` after burning 90 s each.

**This fails `ci-m5-gates.yml`, which is PR-blocking for any change under `iceberg/**` (`.github/workflows/ci-m5-gates.yml:5-13, 57`).** It also runs in `ci-integration.yml` and `ci-nightly.yml`.

The harness docstring already rejects the obvious alternative (row-count waiting) with a valid reason. A replacement liveness signal is needed. Candidates, in order of preference:

1. **A durable cycle receipt.** Once `cycle_id` rows exist in `marts.lakehouse_metrics`, "this deployment completed a cycle" is directly observable as a new `phase='cycle'` row. This is the strongest signal and reuses work the phase is doing anyway. Cost: the harness gains a Postgres dependency — check whether the m5-gates minimal stack starts Postgres. **It does not**: `ci-m5-gates.yml:41` starts only `minio` and `iceberg-rest`. So this option requires adding Postgres to that job, or running the medallion with `METRICS_ENABLED=0` and using a different signal.
2. **Gold snapshot property.** If the skip path is taken, no new snapshot exists — but if the medallion is allowed to *refresh* provenance without rewriting data, we are back to the empty-overwrite trap (§1b: the APPEND half is not elided). Rejected.
3. **A stdout marker line.** The medallion already prints per-cycle (`:1011-1014`, `:993-997`, `:455`). `h.start_medallion` returns a `subprocess.Popen`; the harness could read a line such as `cycle <cycle_id> complete (gold: skipped|rebuilt)`. Simple, no new service, and the printed decision doubles as human-readable evidence. Risk: log-scraping in a test is brittle and AGENTS.md discourages adding verification layers — but this *replaces* one, it does not add one.
4. **Silver snapshot count + a guaranteed first cycle.** Weakest; the scenario is specifically about cycles that change nothing.

**Recommendation for the planner:** treat "replace `wait_for_new_gold_snapshot`" as a **prerequisite task in the same wave as GLD-01**, with option 3 as the default and option 1 if Postgres is added to the m5-gates stack. Do not defer it.

### 4f. Other tests that will need updating (predicted, from static reading)

| Test | Why |
|---|---|
| `tests/test_ops.py:127-140, 202` | Positional insert-parameter tuples. **Guaranteed break** on any DDL/insert change. |
| `tests/test_ops.py:281-455` | If a `phase` Prometheus label is added, every `published(...)` call needs it. |
| `tests/test_b2_medallion.py:135-145, 174-180` | `records[-1]` assumes run_b2's record is last. Still true when `run_b2` is called directly, but the assertions should move to a `phase("b2")` lookup for clarity. |
| `tests/test_m4_gold.py:158-171, 187-188, 191-204` | `records[-1]`; `overwrite_calls == 1`/`== 2` assumptions — `test_switching_gold_source_does_not_mutate_persisted_silver` asserts `gold.overwrite_calls == 2` after two runs over unchanged Silver. **Under GLD-01 the second write is skipped and this becomes `== 1`.** The test's *intent* (persisted Silver untouched) is unaffected; the Gold count assertion must be re-derived. Note this test also runs `gold_source="persisted_silver", shadow=False` — a tuple the rollout matrix forbids — by calling `run()` directly, bypassing `validate_runtime_config`. |
| `tests/features/test_shadow_cutover.py:210-224, 245-270` | `gold.overwrite_calls == 1` in `metrics_published`; `metrics_republished` asserts `overwrite_calls == before + 1`. Both encode "every cycle writes Gold". Under GLD-01 the rollback scenario (`:62-68`), which re-runs over unchanged Silver, changes behaviour. The **feature text itself** ("the daily metrics are published again", `gold_cutover.feature:36`/`shadow_cutover.feature:66`) may need rewording to "the daily metrics still reflect the current business state". |
| `tests/test_medallion.py:264-270` | Legacy path `records[-1]`. `_run_legacy` remains a single-record path, so this is low-risk — but the legacy record must also gain `cycle_id`/`phase='cycle'`. |
| `tests/e2e/test_lakehouse_e2e.py:924-945` | Only if the legacy record's four filter columns change. Should be verified, not assumed. |
| `docs/BDD-COVERAGE-INVENTORY.md` | Maintained inventory referencing `validate_runtime_config`; must track any scenario added/reworded. |

**Coverage gate:** `AGENTS.md` and `.github/workflows/ci-pr.yml:67` enforce `pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90`, currently passing at 93.66%. AGENTS.md is explicit: "new production code in `iceberg/` lands with dependency-free unit coverage" and the threshold must not be lowered. Every new branch in `iceberg_medallion.py` and `iceberg/common/ops.py` needs a unit test that runs without a stack.

---

## Research Question 5 — Non-overlapping vs inclusive durations

### 5a. Exactly what is timed today

`_run_m4` (`iceberg_medallion.py:1047-1126`):

```
t0 = time.monotonic()                                    # :1051
  ├─ _pin_bronze_boundary(catalog)                       # :1062  — FULL Bronze scan → Arrow
  ├─ run_b2(catalog, metrics)                            # :1064
  │     t1 = time.monotonic()                            # :483  (inside run_b2)
  │     ... per-manifest work ...
  │     record(source="medallion", status="success",     # :602-624
  │            silver_duration_ms = now-t1,
  │            duration_ms       = now-t1)               #  ← both equal; no gold_duration_ms
  ├─ build_silver(bronze_boundary.rows)                  # :1066  — FULL legacy rebuild, in memory
  ├─ _read_persisted_silver(catalog)                     # :1075  — FULL Silver scan
  ├─ compare_business_state(...)                         # :1081
t2 = gold_started = time.monotonic()                     # :1098
  ├─ build_gold + _write_gold                            # :1106-1107
t3
  record(status="success",                               # :1109-1126
         duration_ms        = t3-t0,
         silver_duration_ms = t2-t0,      # ← INCLUSIVE of pin + b2 + rebuild + read + compare
         gold_duration_ms   = t3-t2)
```

So today:
- `outer.silver_duration_ms` **strictly contains** `nested.silver_duration_ms` (and also contains the Bronze pin, which is *outside* run_b2's own timer).
- `outer.duration_ms ≈ outer.silver_duration_ms + outer.gold_duration_ms` by construction.
- `nested.duration_ms == nested.silver_duration_ms` (both `now - t1`, `:615` and `:623`).
- `_run_legacy` (`:1023-1044`) uses `cycle["started"]` from inside `_legacy_silver_cycle` (`:965`) and is single-record — already effectively non-overlapping.

Baseline confirmation of inclusiveness: `06-o1-window.json` cycle 4 — nested B2 `silver_duration_ms = 5805`, outer `silver_duration_ms = 29986`. The 5.8 s sits inside the 30.0 s. A naive `sum(silver_duration_ms)` over that cycle yields 35.8 s for 34.5 s of wall time.

### 5b. What each option means for emitted rows

**Inclusive (documented).** Keep timers as-is; add `cycle_id` + `phase`. Rows per cycle:

| phase | duration_ms | contains |
|---|---|---|
| `b2` | t_b2_end − t1 | itself |
| `cycle` | t3 − t0 | everything including `b2` |

Correct queries: `sum(duration_ms) where phase='cycle'`. Wrong query: `sum(duration_ms)` — still double-counts. The requirement "dashboards must not be **able** to double-count" is met only by convention plus documentation.

**Non-overlapping.** Re-base timers into disjoint segments. Rows per cycle:

| phase | segment | duration |
|---|---|---|
| `b2` | t1 → t_b2_end | own work only |
| `shadow` | (t0→t1 Bronze pin) + (t_b2_end → t2: legacy rebuild, persisted read, compare) | the redundant work this phase exists to eliminate |
| `gold` | t2 → t3 | Gold build + write |
| `cycle` | t0 → t3 | the **envelope**, explicitly documented as the roll-up, not a peer |

Then `sum(duration_ms) where phase <> 'cycle'` ≈ `sum(duration_ms) where phase = 'cycle'`, and either is correct. The only wrong query mixes them, and the `phase` column makes that visible in the query text itself. This also **makes the phase's own success measurable**: the `shadow` phase duration is precisely the number SHD-01 is trying to drive to ~0, and the `gold` phase duration is precisely what GLD-01 targets. Under the inclusive scheme, the shadow cost is only recoverable by subtraction.

A wrinkle worth deciding explicitly: the Bronze pin (t0→t1) happens before `run_b2` and is shadow-only work (`:1061-1063` guards it on `GOLD_SOURCE == "legacy" or SHADOW_COMPARE_ENABLED`). Attributing it to the `shadow` phase is honest and keeps the segments contiguous. Alternatively emit a fifth `bronze_pin` phase — more precise, more rows, more schema surface. **Recommend folding it into `shadow`** and saying so in the docs.

### 5c. Cost and error-proneness

| | Inclusive | Non-overlapping |
|---|---|---|
| Thread `cycle_id` through `run_b2` | required anyway | required anyway |
| New timer variables in `_run_m4` | 0 | 2 (`t1`, `t_b2_end`) |
| Change `run_b2`'s record shape | phase kwarg only | phase kwarg only (its timer is already its own) |
| New emission sites | 0 | 1 (`shadow` phase row) |
| Signature changes | `run_b2(catalog, metrics, fs=None)` → add `cycle_id` | same |
| Query correctness | by convention | by construction |
| Measures the phase's own outcome | by subtraction | directly |

The marginal cost of non-overlapping over inclusive is **two `time.monotonic()` calls and one extra `metrics.record()` call**, because `cycle_id` threading — the genuinely invasive part — is mandatory under either option.

Signature-change safety check (VERIFIED): `run_b2` is called from exactly one production site, `iceberg_medallion.py:1064`. Test call sites are all positional 3-arg: `tests/test_b2_medallion.py:125,157,171,187,194,209,233,239,255,266,269,289`. The two stub monkeypatches are `lambda *args: None` (`test_m4_gold.py:119`) and `lambda *args, **kwargs: None` (`test_shadow_cutover.py:90`), both of which absorb an added keyword-only `cycle_id`. Give `cycle_id` a default of `None` meaning "generate my own", so direct `run_b2` unit tests keep working unchanged.

### 5d. Recommendation

**Non-overlapping, with `cycle` documented as the envelope roll-up.**

Trade-off, stated honestly: non-overlapping requires re-basing `_run_m4`'s timers, which means the *historical* meaning of `silver_duration_ms` diverges from the new one. That is a real interpretability cost and it is exactly what TEL-02 exists to absorb. Mitigate by:
- **Not reusing `silver_duration_ms`/`gold_duration_ms` for the new per-phase value.** Put the phase's own duration in `duration_ms` on the phase row and leave the two stage columns populated only on the `cycle` row with their current (inclusive) meaning. Historical rows then remain byte-for-byte interpretable under the documented rule, and no column silently changes meaning mid-table. This satisfies the locked "historical rows stay interpretable" discretion constraint.
- Documenting the rule as **status-qualified and `cycle_id`-qualified**: rows with `cycle_id IS NULL` are pre-Phase-4 and are read under the four-row corrected rule from CONTEXT §P0; rows with `cycle_id IS NOT NULL` are read under the phase rule. A single `cycle_id IS NULL` predicate cleanly separates the two eras — this is a strong argument for `cycle_id` being nullable with no default rather than backfilled.

---

## Research Question 6 — Existing baseline evidence

**VERIFIED. The corrected reading is exactly right.**

`artifacts/b2-rollout/06-o1-window.json` — 10 rows, `source=medallion`, `status=success`, runtime `{SILVER_MODE: b2, GOLD_SOURCE: persisted_silver, SHADOW_COMPARE: 1}`, window 2026-08-10T19:50:06.843792Z → 19:56:18.483663Z (6 m 12 s).

Rows alternate: odd-indexed rows are nested `run_b2` records (`shadow_comparisons=0`, `gold_duration_ms=0`, `work_completed=100`), even-indexed rows are outer `_run_m4` records (`shadow_comparisons=1`, `gold_duration_ms>0`, `work_completed=0`). **10 rows = 5 outer cycles.**

| Cycle | Nested B2 row (ts) | Outer row (ts) | Nested B2 `silver_duration_ms` | Outer `silver_duration_ms` (inclusive) | `gold_duration_ms` | **Cycle total** |
|---|---|---|---|---|---|---|
| 1 | 19:50:06.843 | 19:50:34.376 | 0 | 24 070 | 4 130 | **28 200 ms (28.2 s)** |
| 2 | 19:50:51.082 | 19:51:39.845 | 0 | 45 448 | 5 083 | **50 531 ms (50.5 s)** |
| 3 | 19:52:40.849 | 19:53:17.757 | 0 | 32 341 | 5 572 | **37 913 ms (37.9 s)** |
| 4 | 19:54:24.188 | 19:54:52.266 | **5 805** | 29 986 | 4 521 | **34 507 ms (34.5 s)** |
| 5 | 19:55:52.818 | 19:56:18.483 | 0 | 21 406 | 4 808 | **26 214 ms (26.2 s)** |

Matches the CONTEXT figures exactly: 28.2 / 50.5 / 37.9 / 34.5 / 26.2 s; Gold 4.130–5.572 s ("4.1–5.6 s") on **every** cycle including the four with no work.

Cycle 4 is the only cycle with real work: `files_processed=1`, `keys_processed=1`, `files_planned=1`, `bytes_planned=4422`, `files_added=1`, `bytes_added=4299`, `snapshot_delta=1`. Corroborated by `artifacts/b2-rollout/06-bounded-workload.json`, which records the single deliberately-published event (`nb-order-001`, business_version 2→3) and its outcome (`silver_work_id: 288d37c3…`, `silver_snapshot_id: 3206326457309031755`).

**Pairing arithmetic checks out**, which is what makes the pairing safe rather than assumed: cycle 4's outer row is at 19:54:52.266 with a total of 34.507 s → cycle start ≈ 19:54:17.76; its nested B2 row is at 19:54:24.188 with its own duration 5.805 s → B2 start ≈ 19:54:18.38. The 0.6 s gap is the Bronze pin (`:1062`), which precedes `run_b2` and sits inside t0→t1. Cycle 1: outer at 19:50:34.376 minus 28.200 s → start 19:50:06.18, and its nested row is at 19:50:06.843 with duration 0 — a 0.66 s Bronze pin. Consistent across the window.

**Caveats to carry into the "after" measurement, verbatim from the evidence:**
- The JSON rows **do not include `duration_ms`** (verified: row keys are the 21 fields listed, `duration_ms` absent). Cycle totals above are `silver_duration_ms + gold_duration_ms`, which equals `duration_ms` by construction (`:1121, :1124, :1125`) to within rounding. The "after" artifact should include `duration_ms` explicitly so no derivation is needed.
- Five cycles at demo volume. `06-o1-summary.json` records `non_empty_b2_rows: 1`. **One** cycle did real work. This establishes no scaling relationship whatsoever and the phase's before/after comparison must say so.
- All ten rows are `status: success`. Neither `shadow_failed` nor `failed` appears anywhere in the recorded evidence — confirming CONTEXT §P0 consequence 2.
- The window was produced under a deliberately bounded workload with `orders-streaming` and `iceberg-writer` stopped before and after (`06-bounded-workload.json` → `bounded_services`). The "after" measurement must reproduce the same bounding to be comparable.

**Evidence-artifact precedent to follow.** `06-o1-window.json` / `06-o1-summary.json` / `06-telemetry-gate.json` establish the shape: `schema_version`, `phase`, `plan`, `runtime` before/after, `observation_start`/`observation_end`, `selection` (an explicit statement of *how rows were chosen*), a `workload_artifact` cross-reference, a named `checks` dict with a `failed_checks` list, a `disposition`, and an explicit `reason` string. The Phase-4 "Required evidence artifact" from CONTEXT §Specifics should reuse this shape verbatim rather than inventing one.

---

## Research Question 7 — Validation Architecture

> Required section. `workflow.nyquist_validation` is `true` in `.planning/config.json`.

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 8.4.2 + pytest-bdd (verified: `./.venv/Scripts/python.exe -c "import pytest; print(pytest.__version__)"` → `8.4.2`) |
| Config file | `pytest.ini` (testpaths `tests`, `pythonpath .`, `addopts = -m "not integration and not e2e and not airflow"`) |
| Path shim | `tests/conftest.py:1-6` prepends `iceberg/` to `sys.path` → imports are `writer.iceberg_writer`, `medallion.iceberg_medallion`, `common.ops`, `b2_spike` |
| Quick run command | `uv run --locked pytest -q tests/test_ops.py tests/test_b2_medallion.py tests/test_m4_gold.py tests/test_medallion.py` |
| Full suite command | `uv run --locked ruff check . && uv run --locked black --check . && uv run --locked pytest` |
| Coverage gate | `uv run --locked pytest tests --cov=iceberg --cov-report=term-missing --cov-fail-under=90` (currently 93.66%; must not regress — AGENTS.md §Verification contract) |
| Runtime | uv 0.12.5 (verified), Python 3.12.12 (verified), pyarrow 21.0.0 (verified) |

### Phase Requirements → Test Map

Requirement IDs are taken from `.planning/ROADMAP.md:207-210`. **See §Open Questions Q1 — `TEL-01` collides with an existing Phase-1 requirement.**

| Req | Behaviour to prove | Layer that owns it | Layer exists? | Automated command |
|---|---|---|---|---|
| TEL-01a | One logical run emits exactly one `phase='cycle'` record | unit — `tests/test_m4_gold.py` / `tests/test_medallion.py` via `FakeMetrics` | ✅ | `uv run --locked pytest -q tests/test_m4_gold.py tests/test_medallion.py` |
| TEL-01b | All records from one run share one `cycle_id` | unit, same | ✅ | same |
| TEL-01c | Phase durations are mutually non-overlapping; `cycle` ≥ Σ phases | unit — monkeypatch `m.time.monotonic` with a scripted sequence (precedent: `tests/test_ops.py:407` patches `ops.time.time`) | ✅ | same |
| TEL-01d | Nested B2 time is not double-counted in Prometheus | unit — `tests/test_ops.py` via `published()` | ✅ | `uv run --locked pytest -q tests/test_ops.py` |
| TEL-01e | Snapshot ids (`bronze`/`silver`/`gold`) are recorded where meaningful | unit — `FakeIcebergTable.current_snapshot()` (`b2_fakes.py:160`), `FakeTable.current_snapshot()` (`fakes.py:58`) | ✅ | `uv run --locked pytest -q tests/test_b2_medallion.py tests/test_m4_gold.py` |
| TEL-01f | The `cycle` row is written **last** (protects `postgres_exporter`'s `distinct on (source)`) | unit — assert `records[-1]["phase"] == "cycle"` | ✅ | same |
| TEL-01g | Insert statement and DDL stay additive | unit — `tests/test_ops.py:116-143` (must be rewritten to be **name-keyed, not positional**) | ✅ | `uv run --locked pytest -q tests/test_ops.py` |
| TEL-02a | The status-qualified historical rule classifies all four branches correctly | unit — a pure classifier function in `iceberg/common/` fed the four `(status, gold_duration_ms, cycle_id)` tuples. Making the rule **executable** rather than prose is strongly preferable: it becomes testable, and `scripts/`-free per AGENTS.md "no new verification layer". | ✅ (module exists; function does not) | `uv run --locked pytest -q tests/test_ops.py` |
| TEL-02b | Documentation states the `shadow_failed` / `failed` branches were derived from code, not observed | doc review — `README.md`, `docs/observability/O1-runtime-observability.md` | ✅ | manual (checkpoint) |
| SHD-01a | Unchanged Bronze **and** unchanged Silver ⇒ fast path taken (no legacy rebuild, no compare) | unit — `tests/test_m4_gold.py`, assert `build_silver` not called (monkeypatch-capture idiom already used at `:141-147`) | ✅ | `uv run --locked pytest -q tests/test_m4_gold.py` |
| SHD-01b | Changed Bronze ⇒ receipt invalid ⇒ comparison runs | unit, same | ✅ | same |
| SHD-01c | Changed Silver **independently** (recovery moved it) ⇒ receipt invalid ⇒ comparison runs | unit, same | ✅ | same |
| SHD-01d | Changed runtime/projection identity ⇒ receipt invalid | unit — pure receipt-validity function, no doubles needed | ✅ | same |
| SHD-01e | Missing / unreadable receipt ⇒ comparison runs (fail-safe) | unit | ✅ | same |
| SHD-01f | A comparison that does run still uses the pinned Bronze boundary | unit — the existing test `test_shadow_uses_bronze_boundary_pinned_before_b2_runs` (`tests/test_m4_gold.py:174-188`) already proves this and must stay green | ✅ | same |
| SHD-01g | Shadow mismatch still fails closed before any Gold write | BDD — `shadow_cutover.feature:41-47` (existing, must stay green) | ✅ | `uv run --locked pytest -q tests/features/test_shadow_cutover.py -m bdd` |
| SHD-01h | Receipt survives a process restart | integration — `medallion_harness` two-deployment walk | ✅ (harness exists; needs the §4e liveness fix) | `uv run --locked pytest -q tests/features -m "bdd and integration"` |
| GLD-01a | Unchanged Silver ⇒ Gold not rewritten | unit — `FakeTable.overwrite_calls` | ✅ | `uv run --locked pytest -q tests/test_m4_gold.py` |
| GLD-01b | Changed Silver ⇒ Gold rebuilt | unit, same | ✅ | same |
| GLD-01c | Gold write stamps `source-silver-snapshot-id` | unit — `tests/support/fakes.py:FakeTable.snapshot_properties` (`:42, :67-69`) already captures it | ✅ | same |
| GLD-01d | Absent provenance ⇒ rebuild (covers post-maintenance Gold rewrite) | unit | ✅ | same |
| GLD-01e | Provenance is read from `current_snapshot()` only, never from older snapshots | unit — seed a `FakeTable` with a stale property-bearing snapshot plus a newer bare one | ✅ (`FakeTable.add_snapshot(**summary)`, `fakes.py:50-56`) | same |
| GLD-01f | Gold provenance survives a real catalog round-trip | integration — `gold_cutover.feature` | ✅ (with §4e fix) | `uv run --locked pytest -q tests/features -m "bdd and integration"` |
| POL-01 | Steady-state shadow policy analysis with evidence and safety conditions | **document** — `docs/remediation/` or a new ADR. **No test.** Explicitly an analysis deliverable; the matrix is not changed. | n/a | doc review (checkpoint) |
| PRF-01 | Arrow/Python boundary is measured; optimised only if still measurable | measurement artifact under `artifacts/`; unit tests only if code changes. FF-14 preservation is already covered by `tests/test_m5_fitness_functions.py` and `tests/features/silver_business_state.feature` | ✅ | `uv run --locked pytest -q tests/test_m5_fitness_functions.py tests/features/test_silver_business_state.py` |
| REGR-1 | Crash-before-commit and crash-after-commit recovery still green | unit `tests/test_b2_medallion.py:183-245`; integration `tests/integration/test_m3_b2_recovery.py` | ✅ | `uv run --locked pytest -q tests/test_b2_medallion.py`; `pytest -q -m integration tests/integration/test_m3_b2_recovery.py` |
| REGR-2 | Replay/idempotency still green | `tests/test_b2_medallion.py:247-291`, `tests/features/writer_crash_recovery.feature`, `retention_recovery.feature` | ✅ | `uv run --locked pytest -q tests/features -m bdd` |
| REGR-3 | Silver business-state contract unchanged | `tests/features/silver_business_state.feature` | ✅ | `uv run --locked pytest -q tests/features/test_silver_business_state.py` |
| REGR-4 | Rollout matrix unchanged (P2 is analysis only) | `tests/test_m5_fitness_functions.py:163-180`, `shadow_cutover.feature:17-32` | ✅ | `uv run --locked pytest -q tests/test_m5_fitness_functions.py -m architecture` |
| BENCH-1 | Before/after benchmark on the same bounded workload | evidence artifact under `artifacts/`, following the `06-*` shape. **Requires a live stack and deliberate state mutation** → out of scope for read-only work; must be an explicitly authorised task. | ⚠️ harness exists (`06-bounded-workload.json` documents the procedure) but is manual | manual, authorised |

### Sampling Rate

- **Per task commit:** `uv run --locked ruff check . && uv run --locked black --check .` plus the narrowest relevant test module.
- **Per wave merge:** `uv run --locked pytest` (fast suite, 292 tests baseline) **plus** `uv run --locked pytest tests --cov=iceberg --cov-fail-under=90`.
- **Any wave touching `iceberg/**` or `tests/features/**`:** also `uv run --locked pytest -q tests/features -m "bdd and integration"` and `pytest -q -m integration tests/integration/test_m3_b2_recovery.py tests/integration/test_m4_gold_cutover.py` when the live minimal stack is available and the task authorises it — because `ci-m5-gates.yml` will run them as a PR blocker regardless.
- **Compose/runtime change (only if a volume or env var is added):** `docker compose --env-file .env.example -f docker-compose.yml -f docker-compose.extended.yml config --quiet`.
- **Phase gate:** full completion gate from AGENTS.md, plus the before/after benchmark artifact, plus `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] **`tests/support/fakes.py`** — add `FakeMetrics.phase(name)` / `FakeMetrics.cycle()` accessors so assertions stop using `records[-1]`. Covers TEL-01a/b/f. **Blocks every telemetry test.**
- [ ] **`tests/test_ops.py:116-143, 182-202`** — convert positional insert-parameter assertions to name-keyed. **Guaranteed break otherwise.** Covers TEL-01g.
- [ ] **`tests/support/medallion_harness.py:181-200`** — replace `wait_for_new_gold_snapshot` with a liveness signal that does not assume every cycle writes Gold. **Blocks GLD-01 from landing without breaking a PR-blocking CI gate.** Covers GLD-01f, SHD-01h.
- [ ] **`tests/test_m4_gold.py:76-89`** — the local `FakeTable` has no `current_snapshot()` and discards `snapshot_properties`; either extend it or switch to `tests/support/fakes.py:FakeTable`. Covers GLD-01c/e.
- [ ] **Deterministic clock helper** — a monkeypatch of `m.time.monotonic` returning a scripted sequence, so phase-duration non-overlap is asserted on exact integers rather than timing luck. Precedent: `tests/test_ops.py:403-418`. Covers TEL-01c.
- [ ] **No new framework, runner, or wrapper script.** AGENTS.md: "Do not add a test framework, task runner, wrapper script, or verification layer unless the requested change explicitly requires it." Nothing here requires one.

---

## Standard Stack

**No new dependency is required or recommended for this phase.** Everything the locked decisions need is already installed and pinned.

### Core (all already present)

| Library | Pinned version | Purpose here | Evidence |
|---|---|---|---|
| `pyiceberg[pyarrow]` | 0.11.1 | `Table.overwrite(..., snapshot_properties=...)` for Gold provenance; `snapshot.summary.additional_properties` for reads | `iceberg/requirements.in:1`, `pyproject.toml:14`; runtime signature verified |
| `pyiceberg-core` | 0.7.0 | transitive | `iceberg/requirements.in:2` |
| `pyarrow` | 21.0.0 (host venv, verified) | all frame work; `FakeFS`/`FileSelector` doubles | `iceberg/requirements.txt` |
| `psycopg2` | already used | metric + receipt writes | `iceberg/common/ops.py:8` |
| `prometheus_client` | already used | `_RuntimeMetrics` | `iceberg/common/ops.py:234-236` |
| `pytest` | 8.4.2 | all layers | verified |
| `pytest-bdd` | installed | feature files | `tests/features/test_*.py` imports |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Postgres receipt table | Iceberg snapshot property on Silver | Rejected — writing a Silver snapshot to record a validation outcome violates the "persisted Silver is not rewritten" contract (`test_shadow_cutover.py:240-242`, `test_gold_cutover.py:167-175`). |
| Postgres receipt table | MinIO object, completion-ledger style | Viable runner-up. Reuses `FakeFS` (`b2_fakes.py:63-84`) for free unit testing and needs no new Postgres DDL. Loses operator queryability. Choose if the plan wants to avoid touching `ops.py`'s DDL twice. |
| New Postgres table | More columns on `marts.lakehouse_metrics` | Rejected — the receipt is a *current-state certification* (one row, upserted), not an append-only event. Mixing lifecycles in one table makes both queries harder and worsens the existing ~970 rows/day growth. |
| `uuid.uuid4().hex` for `cycle_id` | monotonic counter, or `metric_ts` | Use `uuid.uuid4().hex` — direct precedent at `iceberg_writer.py:438` (`load_id = uuid.uuid4().hex`). A counter needs durable state; a timestamp is not unique under a restart-storm. |
| Adding `phase` as a Prometheus label | Emitting runtime metrics only for the `cycle` phase | See §2c — the second option is cheaper and fixes the existing gauge-reset defect; the first is more faithful to the locked wording. Either is defensible; state the choice in `docs/observability/O1-runtime-observability.md`. |

**Installation:** none.

---

## Package Legitimacy Audit

**Not applicable — this phase installs no external packages.**

Every capability required by the locked decisions is satisfied by dependencies already pinned with hashes in `iceberg/requirements.txt` and `requirements-dev.txt`. `slopcheck` was therefore not run: there is no candidate package to audit. Should the planner discover a genuine need for a new dependency, the Package Legitimacy Gate must be executed before it enters any plan, and the lock-regeneration path in `CLAUDE.md` §Dependency management applies (nine generated lock files, `ci-pr.yml` enforces `git diff --exit-code`).

---

## Architecture Patterns

### Current cycle flow (verified against source)

```text
run(catalog, metrics, mode)                                    :1129
 ├─ mode == "b2" ─────────────────────────────► _run_m4        :1136
 └─ mode == "legacy"
      ├─ GOLD_SOURCE=legacy AND not SHADOW ───► _run_legacy    :1141
      └─ otherwise ─────────────────────────► _run_m4          :1143

_run_m4(catalog, metrics, selected_mode)                       :1047
 │  t0
 ├─[b2] _pin_bronze_boundary ──► FULL Bronze scan → Arrow      :1062   ← redundant when nothing moved
 │      run_b2 ──────────────► per-manifest incremental Silver :1064   ← emits nested metric :602
 │      build_silver(pinned) ─► FULL legacy rebuild in memory  :1066   ← redundant when nothing moved
 ├─[legacy] _legacy_silver_cycle ► FULL rebuild + Silver write :1068   ← emits :979 on fail
 │  _read_persisted_silver ───► FULL Silver scan               :1075
 │  SHADOW? compare_business_state                             :1081   ← redundant when nothing moved
 │          mismatch ⇒ record(shadow_failed) + raise           :1089-1096
 │  t2 = gold_started
 │  build_gold(gold_input); _write_gold ─► FULL Gold overwrite :1106-1107 ← redundant when Silver unmoved
 │  record(success, duration/silver/gold)                      :1109
```

The four `← redundant` markers are exactly the work SHD-01 and GLD-01 remove. Note the Bronze pin, the legacy rebuild and the compare are gated together on `GOLD_SOURCE == "legacy" or SHADOW_COMPARE_ENABLED` (`:1061`), so a single receipt-valid check can short-circuit all three — but `_read_persisted_silver` (`:1075`) is **unconditional** and is still needed to serve Gold at cutover. Do not accidentally skip it.

### Pattern 1 — Additive metric schema evolution (established, follow exactly)

```python
# Source: iceberg/common/ops.py:19-68
METRICS_DDL = """
create table if not exists marts.lakehouse_metrics ( ... );
alter table marts.lakehouse_metrics add column if not exists work_available bigint not null default 0;
...
"""
```
Both statements run in one `cur.execute` (`:98`) guarded by a `schema_ready` latch (`:94-99`). New columns go in **both** the `create table` body (for fresh databases) **and** an `add column if not exists` line (for existing ones). Governing precedent: `docs/remediation/M5-fitness-functions-and-cutover-gates.md:33-34`.

For `cycle_id`/`phase` prefer `text` **nullable, no default** — a `not null default ''` would erase the clean `cycle_id IS NULL` predicate that separates pre- and post-Phase-4 rows (§5d).

### Pattern 2 — Snapshot-property provenance write + re-check (established, mirror exactly)

```python
# Source: iceberg/writer/iceberg_writer.py:458-461 (append) and :356-359 (re-check)
table.append(arrow_table, snapshot_properties={LOAD_ID_KEY: load_id})
...
for snapshot in table.metadata.snapshots:
    load_id = snapshot.summary.additional_properties.get(LOAD_ID_KEY)

# Source: iceberg/medallion/iceberg_medallion.py:562-571 (overwrite) and :307-315 (re-check)
silver.overwrite(frame, overwrite_filter=In(...), snapshot_properties={SILVER_WORK_ID_KEY: load_id, ...})
...
work_id = snapshot.summary.additional_properties.get(SILVER_WORK_ID_KEY)
```

Gold differs in one deliberate way: read **only** `current_snapshot()`, not the whole history, so a Trino maintenance rewrite invalidates provenance instead of a stale snapshot vouching for it (§1b).

### Pattern 3 — Immutable, ambiguity-intolerant receipt (established)

```python
# Source: iceberg/medallion/iceberg_medallion.py:245-288
existing = _read_json(fs, path)          # read-before-write
if existing is not None:
    if str(existing.get("load_id")) != load_id or existing.get("manifest_id") != ...:
        raise ValueError(f"Ambiguous completion identity for {load_id}")
    return existing                       # idempotent
```
and on load (`:239-240`): `raise ValueError(f"Ambiguous completion receipts for {load_id}")`.

**Ambiguity is a hard error, not a warning.** A shadow receipt must inherit this: two receipts claiming different outcomes for the same `(bronze_snapshot_id, silver_snapshot_id, runtime_identity)` is a bug that must surface, not be silently resolved by "latest wins".

### Pattern 4 — Best-effort observability, fail-closed correctness (established)

`Metrics.record` swallows every exception (`ops.py:210-215`) and prints to stderr; the docstring contract is in `CLAUDE.md:151` and `docs/remediation/M5-...:64-65`. **The receipt read must not inherit this.** Explicit rule for the plan: *a failure anywhere in the receipt path degrades to doing the full work, never to skipping it.*

### Anti-Patterns to Avoid

- **Empty `overwrite` to refresh provenance.** The APPEND half is not elided for an empty frame (`snapshot.py:521-547`), so it writes a snapshot anyway — defeating the skip and growing snapshot history. (§1b)
- **Reading Gold provenance by walking snapshot history.** Fail-open: an expired or superseded snapshot could vouch for a Gold state that maintenance has since rewritten. (§1b)
- **Skipping on Bronze identity alone.** Explicitly forbidden by CONTEXT §P1 and independently justified: Silver moves through B2 recovery (`:502-512`) without Bronze moving.
- **Reusing `silver_duration_ms` for a phase-scoped value.** Silently changes the meaning of 8,800 historical rows. (§5d)
- **`records[-1]` in new tests.** Ambiguous the moment multiple records exist per run. (§4a)
- **Adding `(b2, persisted_silver, 0)` to `RUNTIME_ROLLOUT_MATRIX`.** Explicitly forbidden by CONTEXT §P2. `tests/test_m5_fitness_functions.py:171-180` and `shadow_cutover.feature:29-32` both assert its absence.
- **Backfilling `cycle_id` onto historical rows.** Destroys the era-separating predicate and misrepresents un-instrumented runs as instrumented.

### Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Durable per-commit provenance | A sidecar manifest keyed by table name | `snapshot_properties` + `snapshot.summary.additional_properties` | Atomic with the commit; already proven in-repo; survives arbitrary crash points. A sidecar can disagree with the table. |
| Unique cycle identity | Counter in a state file | `uuid.uuid4().hex` (`iceberg_writer.py:438`) | No durable state needed; collision-free across restarts. |
| Idempotent receipt upsert | Read-modify-write from Python | `insert ... on conflict (...) do update set ...` (`dags/lakehouse_maintenance.py:127-136`) | Single round trip, no lost-update race. |
| Metric schema migration | A migration framework | `alter table ... add column if not exists` in `METRICS_DDL` | Established repo idiom; explicitly ratified in `docs/remediation/M5-...:33-34`. AGENTS.md forbids adding a new tooling layer. |
| Prometheus sample assertions | Counting mock calls | `published(collector, name, **labels)` (`tests/test_ops.py:32-44`) | Proves the value an operator actually sees, including its label set. |
| Object-store fakes for receipt tests | New mocks | `tests/support/b2_fakes.py:FakeFS` (`:63-84`) | Already implements `get_file_info` / `open_input_file` / `open_output_stream` / `delete_file` against the exact `S3FileSystem` slice the medallion uses. |
| Deterministic timing in tests | `sleep` | monkeypatch `m.time.monotonic` (precedent `tests/test_ops.py:407`) | Exact assertions; no flake. |

---

## Common Pitfalls

### Pitfall 1: The Gold-snapshot liveness assumption in the integration harness
**What goes wrong:** `ci-m5-gates.yml` fails on the PR that lands GLD-01, after burning 90 s per stage in `wait_for_new_gold_snapshot`.
**Why it happens:** `tests/support/medallion_harness.py:186` hard-codes the invariant "Every cycle ends in a Gold overwrite" as the proof a deployment ran.
**How to avoid:** Land the replacement liveness signal in the same wave. Do not defer.
**Warning signs:** `AssertionError: <ns>.gold gained no snapshot within 90s — the deployment never completed a cycle`.

### Pitfall 2: Positional insert-parameter assertions
**What goes wrong:** `tests/test_ops.py` fails with a tuple-length or index mismatch as soon as a column is added.
**Why it happens:** `:127-140` asserts `log[1][1][:11] == (...)` and `log[1][1][11:] == (0,) * 17`; `:202` asserts `log[1][1][11:21] == (...)`.
**How to avoid:** Convert to name-keyed assertions **before** touching `METRICS_DDL`, as a standalone refactor commit.
**Warning signs:** `assert (..., 0, 0) == (..., 0)`.

### Pitfall 3: The exporter's `distinct on (source)` silently changes meaning
**What goes wrong:** `lakehouse_source_last_duration_seconds{source="medallion"}` starts reporting a phase duration; `LakehouseUnresolvedWork`'s freshness clause reads a phase row's timestamp.
**Why it happens:** `observability/postgres_exporter.py:46-54` picks the newest row per `source`, and `phase` is not in the key.
**How to avoid:** Guarantee by test that the `phase='cycle'` record is written last, **or** add `where phase = 'cycle' or phase is null` to the exporter query. The second is more robust; the first is required anyway for the metric ordering to be sane.
**Warning signs:** Grafana "Source availability" flapping, or durations that suddenly drop by an order of magnitude.

### Pitfall 4: New `status` literals silently breaking gauges and alerts
**What goes wrong:** `SOURCE_UP` goes to 0, or `LakehouseApplicationFailure` fires spuriously.
**Why it happens:** `postgres_exporter.py:58-60` hard-codes `{"success","ok","noop"}`; `alerts.yml` keys `increase(lakehouse_events_total{status="failed"}[10m]) > 0`.
**How to avoid:** Prefer **not** to introduce new status values. Express "the fast path was taken" as a *phase* attribute or a boolean column (`shadow_skipped`, `gold_skipped`), not as a status. If a new status is unavoidable, update both the exporter set and the alert rules in the same commit.
**Warning signs:** A red "Source availability" panel with a green pipeline.

### Pitfall 5: ADR-0001 D-4 contradiction
**What goes wrong:** A ratified ADR says the opposite of what the code now does.
**Why it happens:** `docs/adr/0001-incremental-silver-and-gold.md:468` — "**Gold is not made incremental. It is rebuilt in full from persisted Silver on every cycle.**"
**How to avoid:** Amend the ADR in this phase with a superseding note. The right framing: D-4's *invariant* — Gold state is always the exact full rebuild of the current persisted Silver — is preserved; what changes is that a rebuild producing a byte-identical result is elided. The six reasons listed in D-4's table (`:470-476`) all remain true and none of them is an argument for rebuilding when nothing changed. Get this wording reviewed rather than asserted.
**Warning signs:** None automated — this is a documentation-integrity failure, which is precisely why it must be planned.

### Pitfall 6: The medallion's existing durable state being overlooked
**What goes wrong:** A plan adds a `/state` volume "because the medallion has no durable state", duplicating a mechanism that already exists in MinIO.
**Why it happens:** The medallion has no Docker volume, which reads as "no state" — but `progress.json` and the completion ledger are durable S3 objects (`:59-65`, `:195-242`).
**How to avoid:** §3a.
**Warning signs:** A compose diff in a phase that should not need one.

### Pitfall 7: A stale projection version certifying a changed contract
**What goes wrong:** `SHADOW_BUSINESS_COLUMNS` or `compare_business_state` changes, the receipt still matches, and the fast path skips validation of a comparison rule that no longer exists.
**Why it happens:** A hand-maintained version constant is not coupled to the thing it versions.
**How to avoid:** Derive the projection identity partly from a hash of `SHADOW_BUSINESS_COLUMNS + SHADOW_EXCLUDED_COLUMNS` (`:780-793`) so the most likely real change invalidates receipts automatically, and keep a hand-bumped constant for semantic changes the tuple cannot see. Add a unit test that changing the tuple changes the identity.
**Warning signs:** None at runtime — that is the danger.

### Pitfall 8: `_snapshot_id` returning `None` and comparing equal
**What goes wrong:** `None == None` for a Bronze/Silver/Gold table with no snapshots ⇒ the fast path fires on an empty lake.
**Why it happens:** `_snapshot_id` (`:931-938`) legitimately returns `None` for a table with no current snapshot, and the `test_m4_gold.py` local double returns `None` always.
**How to avoid:** Treat any `None` snapshot id as "cannot certify" — never as a match. Unit-test it explicitly.
**Warning signs:** Gold never built on a fresh stack.

---

## Code Examples

All examples below are **existing repository code**, quoted to establish the pattern. No new API is introduced.

### Stamping and re-reading a custom snapshot property via `overwrite`
```python
# Source: iceberg/medallion/iceberg_medallion.py:562-573
silver.overwrite(
    _rows_to_silver(resolved),
    overwrite_filter=In("order_id", sorted({row["order_id"] for row in resolved})),
    snapshot_properties={
        SILVER_WORK_ID_KEY: load_id,
        "changed-keys": str(len(resolved)),
    },
)
snapshot = silver.current_snapshot()
snapshot_id = snapshot.snapshot_id if snapshot else None
```
```python
# Source: iceberg/medallion/iceberg_medallion.py:307-315
def silver_committed_work_ids(silver) -> dict[str, int]:
    committed: dict[str, int] = {}
    for snapshot in silver.metadata.snapshots:
        if not snapshot.summary:
            continue
        work_id = snapshot.summary.additional_properties.get(SILVER_WORK_ID_KEY)
        if work_id:
            committed[work_id] = snapshot.snapshot_id
    return committed
```

### Snapshot id with a test-double-tolerant fallback (already exists — reuse it)
```python
# Source: iceberg/medallion/iceberg_medallion.py:931-938
def _snapshot_id(table) -> int | None:
    current_snapshot = getattr(table, "current_snapshot", None)
    if callable(current_snapshot):
        snapshot = current_snapshot()
        if snapshot is not None:
            return getattr(snapshot, "snapshot_id", None)
    metadata = getattr(table, "metadata", None)
    return getattr(metadata, "current_snapshot_id", None)
```

### Idempotent Postgres receipt upsert
```python
# Source: dags/lakehouse_maintenance.py:125-137
cur.execute(AUDIT_DDL)
cur.execute(
    """
    insert into marts.maintenance_runs (
        run_id, run_ts, table_name, before_snapshots, after_snapshots, status
    ) values (%s, now(), %s, %s, %s, %s)
    on conflict (run_id, table_name) do update set
        run_ts = excluded.run_ts,
        before_snapshots = excluded.before_snapshots,
        after_snapshots = excluded.after_snapshots,
        status = excluded.status
    """,
    (...),
)
```

### Asserting a Prometheus sample rather than a call count
```python
# Source: tests/test_ops.py:32-44
def published(collector, name: str, **labels: str) -> float:
    for metric in collector.collect():
        for sample in metric.samples:
            if sample.name == name and sample.labels == labels:
                return sample.value
    raise AssertionError(f"no sample {name} with labels {labels}")
```

### Capturing a call to prove which projection was used (identity, not equality)
```python
# Source: tests/test_m4_gold.py:140-154
gold_inputs = []
real_build_gold = m.build_gold

def capture_gold_input(df):
    gold_inputs.append(df)
    return real_build_gold(df)

monkeypatch.setattr(m, "build_gold", capture_gold_input)
m.run(catalog, metrics, "b2")
assert gold_inputs[0] is persisted_silver.df
```

---

## State of the Art

| Old approach (in this repo) | Current approach the phase moves to | Impact |
|---|---|---|
| One `source="medallion"` identity for both nested and outer executions | `cycle_id` + `phase` distinguish them | Removes the double-count in Postgres and the gauge-reset in Prometheus |
| Inclusive `silver_duration_ms` on the outer record | Non-overlapping phase durations, `cycle` as documented envelope | Query correctness by construction |
| Full Bronze scan + legacy rebuild + compare every cycle under `SHADOW_COMPARE=1` | Receipt-gated fast path | Removes ~20–45 s per no-op cycle at the measured baseline |
| Gold overwritten every cycle regardless of Silver | Skip when `source-silver-snapshot-id` matches current Silver | Removes 4.1–5.6 s per no-op cycle at the measured baseline |
| ADR-0001 D-4 "rebuilt in full ... on every cycle" | "rebuilt in full whenever persisted Silver moves; an identical rebuild is elided" | ADR amendment required |

**Not deprecated, explicitly retained:** `RUNTIME_ROLLOUT_MATRIX` and its four states; `_pin_bronze_boundary` when a comparison actually runs; FF-14 semantics; the writer's `load-id` idiom; `Metrics.record` best-effort semantics; the completion ledger.

---

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---|---|---|
| uv | all Python commands | ✅ | 0.12.5 (exact pin satisfied) | — |
| Python (project venv) | fast suite | ✅ | 3.12.12 | — |
| pytest | all test layers | ✅ | 8.4.2 | — |
| pyarrow | frames + doubles | ✅ | 21.0.0 | — |
| pyiceberg | provenance mechanism | ✅ | 0.11.1 | — |
| psycopg2 / prometheus_client | metrics | ✅ | installed in host venv | — |
| Docker CLI | integration/E2E gates | ✅ present, **deliberately not invoked** | — | — |
| Live MinIO + Iceberg REST | `-m integration`, `bdd and integration` | ⚠️ **not verified** — probing would require starting services | — | Unit layer covers every locked behaviour except cross-restart durability; integration is the CI gate. |
| Live PostgreSQL | receipt round-trip, E2E | ⚠️ **not verified** | — | Fake-based unit coverage; note `ci-m5-gates.yml:41` starts **only** minio + iceberg-rest, so any harness change depending on Postgres needs that job extended. |
| sqlalchemy | offline PyIceberg catalog for a write/read probe | ❌ **absent** | — | None needed — Evidence C/D in §1a supersede it. Do **not** add it as a dependency for this. |

**Missing with no fallback:** none.

---

## Security Domain

> `workflow.security_enforcement: true`, `security_asvs_level: 1`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control in this phase |
|---|---|---|
| V2 Authentication | no | No new authenticated surface. Postgres and MinIO credentials continue to come from `.env` only (`AGENTS.md` §Runtime safety). |
| V3 Session Management | no | No sessions. |
| V4 Access Control | no | No new endpoint. The Prometheus endpoint (`ops.py:299`, `start_http_server(port, addr="0.0.0.0")`) already exists unchanged and is bound inside the compose network. |
| V5 Input Validation | **yes** | Any new receipt read must validate before trusting. Follow `list_bronze_work` (`:186-187`, `raise ValueError` on a malformed record) and `load_completion_ledger` (`:236-241`, rejects a receipt with no `load_id`, a non-`success` result, or an ambiguous duplicate). Snapshot-property values are `str` and must be parsed defensively — an unparsable `source-silver-snapshot-id` means "no provenance", i.e. rebuild. |
| V6 Cryptography | no (advisory) | The existing `hashlib.sha256` digest helper (`_rows_output_digest`, `:291-293`) is an integrity digest, not a security control. If a projection-version hash is added, reuse `hashlib.sha256` — never hand-roll. |
| V7 Error Handling / Logging | **yes** | `Metrics.record` prints exception text to stderr (`ops.py:211-214`) and the shadow mismatch path dumps the full mismatch JSON (`:1083-1088`). These carry business data (`order_id`, `customer`, `amount`) into logs. Any new receipt-failure log must not widen that: log identifiers and counts, not payloads. |
| V14 Configuration | **yes** | No credential may be hard-coded (AGENTS.md). New env vars must be declared in `docker-compose.extended.yml`, `.env.example` and `docs/CONFIGURATION.md` — note `MEDALLION_COMPLETION_LEDGER_PREFIX` is currently declared in none of them, a gap not to repeat. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard mitigation | Status in this phase |
|---|---|---|---|
| SQL injection into the metrics/receipt insert | Tampering | Parameterised `%s` placeholders throughout (`ops.py:160-209`, `lakehouse_maintenance.py:125-137`) | Follow the existing pattern; never f-string a value into SQL. Note `_write_gold`-adjacent code and `test_lakehouse_e2e.py:517` do use f-strings for **table identifiers** — acceptable there because the identifiers are code constants, not input. |
| Forged / ambiguous receipt causing validation to be skipped | Spoofing / Elevation | Ambiguity is a hard error (`:239-240`, `:264-269`); fail-safe default is "run the full work" | **This is the primary security-relevant property of the phase.** A skipped shadow comparison is a skipped correctness gate. Encode as an explicit invariant + test. |
| Stale provenance vouching for a superseded Gold state | Repudiation / Tampering | Read `current_snapshot()` only; treat absent/unparsable as no provenance | §1b |
| Log injection / sensitive data in logs | Information disclosure | Log ids and counts, not payloads | Existing mismatch dump already logs payloads — do not widen it; consider noting it as a pre-existing observation rather than fixing it in scope. |
| Metrics endpoint exposure | Information disclosure | Bound to the compose network; ports are host-mapped only for prometheus/grafana/exporter | Unchanged. |

No ASVS L1 blocker identified for this phase.

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | `sum(silver_duration_ms + gold_duration_ms)` equals the outer `duration_ms` to within rounding for the baseline rows | Q6 | Low. It follows from `:1121/:1124/:1125`, but the artifact omits `duration_ms` so it could not be checked against recorded data. The "after" artifact should record `duration_ms` directly. |
| A2 | The paired-row reading (odd = nested B2, even = outer) holds for all five cycles | Q6 | Low — cross-checked arithmetically for cycles 1 and 4 (start-time reconstruction matches the Bronze-pin gap). Not proven for a window containing a `failed` row, where CONTEXT §P0 says no outer record exists at all. |
| A3 | Adding a `phase` label to Prometheus collectors requires updating ~20 `published(...)` call sites | Q4b, Q2c | Low — counted by reading `tests/test_ops.py:281-455`. Exact count may differ slightly. |
| A4 | `ci-m5-gates.yml` will fail (not merely slow down) once GLD-01 lands | Q4e | Low. `wait_for_new_gold_snapshot` raises `AssertionError` on timeout (`:197-200`) and `run_deployment` calls it unconditionally (`:224`). Could only be wrong if some other force causes a Gold snapshot during those stages — nothing in the code path does. **Not empirically confirmed** (would require running the integration suite against a live stack). |
| A5 | `_read_persisted_silver` must remain unconditional even under the fast path | Architecture Patterns | Low — Gold at cutover reads `persisted_silver_df` (`:1104`). Would be wrong only if the plan also skips Gold in the same cycle, in which case the read is genuinely unnecessary. Worth an explicit decision. |
| A6 | Postgres is not available in the `ci-m5-gates.yml` job | Q4e, Env | Low — `.github/workflows/ci-m5-gates.yml:41` starts `minio iceberg-rest` only. Not runtime-verified. |
| A7 | `lakehouse_metrics` row growth roughly doubles-to-quadruples with phase rows | Q2b | Medium — extrapolated from `260816-dsi-FINDINGS.md:141-145` (~970 rows/day) times the number of phase rows per cycle. Depends on the final phase count and the medallion interval. Directionally certain, numerically approximate. |
| A8 | The `06-*` artifact shape is the right template for the Phase-4 evidence artifact | Q6 | Low — it is the only precedent, and CONTEXT §Specifics asks for a superset of its fields. |

---

## Open Questions (RESOLVED)

**All five questions below were decided before Phase 4 planning completed.** Each carries
its resolution and the artifact that decided it. The question text is left as written so
the reasoning that produced the decision stays auditable; where a decision went **against**
this document's recommendation that is stated explicitly rather than left for a reader to
notice.

1. **Requirement-ID collision: `TEL-01` is already taken.**
   - What we know: `.planning/REQUIREMENTS.md:30` defines `TEL-01` as a **Phase 1** requirement, status **Complete** ("O1 captures representative B2 files planned, bytes planned, ..."), and `:76` maps it to Phase 1. `.planning/ROADMAP.md:207-210` lists Phase 4's requirements as `[TEL-01 cycle_id and phase separation, TEL-02 ..., SHD-01, GLD-01, POL-01, PRF-01]` — reusing `TEL-01` for a different requirement.
   - What is unclear: whether this is an intentional continuation or an accidental collision. Note also that **Phase 3's requirements were never added to `REQUIREMENTS.md`** (no `FRESH-*` IDs exist), so the file is already stale — the collision may simply have gone unnoticed.
   - Recommendation: the planner should rename the Phase-4 identity metric requirement (e.g. `CYC-01` / `TEL-03`) and register all six Phase-4 IDs plus the missing Phase-3 IDs in `REQUIREMENTS.md` and its traceability table. Do not silently overload a Complete requirement.
   - **RESOLVED — adopted.** Decided in `04-CONTEXT.md:7-11`: the Phase-4 requirement
     is `MTL-01`, and `MTL-02` replaces the proposed `TEL-02`. Registration of all
     seven Phase-4 IDs in `.planning/REQUIREMENTS.md` and its traceability table is
     planned as `04-07-PLAN.md` Task 2, which also records that Phase 3's IDs remain
     absent rather than inventing them. `TEL-01`'s Phase-1 `Complete` row is left
     untouched.

2. **How should "the daily metrics are published again" be re-worded?**
   - What we know: `gold_cutover.feature:36` and `shadow_cutover.feature:66` both encode a Gold *write* as the observable. `test_shadow_cutover.py:219-224` asserts `overwrite_calls == before + 1`.
   - What is unclear: whether the operator wants the scenario to keep asserting a write (which would require an exception to GLD-01 on a Gold-source switch) or to assert *state correctness* instead.
   - Recommendation: reword to assert the state ("the daily metrics still reflect the current business state") and prove non-rewrite separately. But this is a **contract text change** to a ratified feature file — surface it for approval rather than deciding it in a plan.
   - **RESOLVED — adopted, and narrowed.** The operator locked the reword in
     `04-CONTEXT.md` §"Operator decisions taken at planning time (LOCKED)"; it is
     planned as `04-05-PLAN.md` Task 3, covering `tests/features/shadow_cutover.feature:66`
     and its step at `tests/features/test_shadow_cutover.py:219`.
   - **Correction to this document:** the reference above to `gold_cutover.feature:36`
     is **wrong**. Line 36 of that file is `Then the daily metrics are unchanged`,
     which is already a state assertion. `gold_cutover.feature` is therefore pinned
     byte-identical by `04-05-PLAN.md` and is not reworded.
   - **Honesty note carried into the plan:** because GLD-01 is scoped to
     `GOLD_SOURCE=persisted_silver` and this feature's in-memory Silver double has no
     snapshots (so `_snapshot_id` returns `None` and Gold is never certified), the
     original wording would have kept passing. The reword is a locked contract-clarity
     change, not a repair of a break, and `04-05-PLAN.md` requires the summary to say so.

3. **Prometheus: `phase` label, or cycle-only observation?**
   - What we know: both satisfy "dashboards must not double-count"; the trade-off is fully characterised in §2c.
   - What is unclear: whether the operator values live per-phase visibility enough to pay for the dashboard/alert/test churn.
   - Recommendation: default to cycle-only observation plus roll-up (cheaper, fixes more existing defects); flag for the operator during plan review.
   - **RESOLVED — adopted, and locked by the operator.** `04-CONTEXT.md`
     §"Prometheus — cycle-only gauge updates" makes cycle-only observation a locked
     decision and forbids adding a `phase` label to the gauges. Implemented as
     `04-02-PLAN.md` Task 2 (guard `self.runtime.observe` on
     `phase in (None, "cycle")`), with the `B2Outcome` roll-up from `04-03-PLAN.md`
     Task 1 supplying the cycle row's physical-cost values so the gauges stop reading
     zero. No label set, Grafana target or alert expression changes; the exclusion is
     documented as a contract in `04-07-PLAN.md` Task 1.

4. **Does the shadow fast path also skip `_read_persisted_silver`?**
   - What we know: it is unconditional today (`:1075`) and is Gold's input at cutover (`:1104`).
   - What is unclear: whether skipping Gold implies skipping the Silver read in the same cycle.
   - Recommendation: skip it **only** when the Gold rebuild is also skipped in the same cycle; otherwise keep it. Make this an explicit, tested decision rather than an emergent one.
   - **RESOLVED — not adopted.** `04-06-PLAN.md` Task 2 keeps `_read_persisted_silver`
     **unconditional**. Coupling it to the Gold skip would entangle SHD-01 and GLD-01
     into one conditional and make each harder to test alone, and the new `shadow`
     phase duration now measures the read directly, so eliding it later can be decided
     on evidence instead of guesswork. The decision and its reasoning are required to
     be written into the code as a comment.
   - **RESOLVED AGAINST THE RECOMMENDATION — where the receipt lives.** §3d recommends
     a PostgreSQL `marts` table for the shadow certification receipt. `04-06-PLAN.md`
     rejects that and puts the receipt in the medallion's own MinIO state instead, next
     to `progress.json` and the completion ledger, at `MEDALLION_SHADOW_RECEIPT_PATH`.
     Three reasons, all checkable:
     1. `.github/workflows/ci-m5-gates.yml:41` starts only `minio iceberg-rest`, and
        `tests/support/medallion_harness.py:128` sets `METRICS_ENABLED: "0"`. A
        PostgreSQL receipt would make the fast path unreachable in every integration
        proof this repository has, and SHD-01h — *the receipt survives a process
        restart* — unprovable in the only gate that could prove it.
     2. `Metrics.record` swallows every exception by design so observability can never
        break ingestion. The receipt read must do the opposite and fail toward doing
        the work. Keeping the certificate out of the observability object keeps those
        two contracts in separate homes.
     3. `tests/support/b2_fakes.py:FakeFS` already models the exact `S3FileSystem`
        slice the medallion uses, so unit coverage of the receipt path is free.

     Accepted cost, stated plainly: an operator cannot query the certificate with SQL.
     Mitigated because the *decision* it drives — `shadow_skipped`,
     `shadow_comparisons` — is recorded on the metric rows in PostgreSQL, which is
     where operators already look. §3b option A, §3d and the original Architectural
     Responsibility Map row are superseded; see the amendment note under that map.

5. **Is the before/after benchmark (BENCH-1) in scope for this phase's execution?**
   - What we know: CONTEXT §Specifics requires it. It needs a live stack, a bounded Kafka publish, and deliberate state mutation — all forbidden under read-only analysis and all requiring explicit authorisation per AGENTS.md §Runtime safety.
   - Recommendation: plan it as an explicitly authorised, human-gated task at the end of the phase, following the `06-bounded-workload.json` procedure (stop `orders-streaming` and `iceberg-writer`, publish one event, restore). Do not fold it into a routine implementation task.
   - **RESOLVED — adopted.** BENCH-01 is `04-09-PLAN.md`, the phase's only
     `autonomous: false` plan, gated by a blocking `checkpoint:human-action` that
     enumerates every mutation before anything starts. Refusal is a sanctioned outcome
     recorded as `disposition: "NOT MEASURED"`, and `04-10-PLAN.md` Task 2 carries an
     explicit branch for that case so PRF-01 stays deliverable when the benchmark is
     refused.

---

## Sources

### Primary (HIGH confidence — read directly, this session)

**Repository source**
- `iceberg/medallion/iceberg_medallion.py` (full, 1161 lines) — all six metric sites, run_b2, _pin_bronze_boundary, _legacy_silver_cycle, _write_gold, _run_legacy, _run_m4, run, progress/ledger state
- `iceberg/common/ops.py` (full) — `METRICS_DDL`, `Metrics.record`, `_RuntimeMetrics`
- `iceberg/common/cutover.py` (full) — `RUNTIME_ROLLOUT_MATRIX`, `validate_runtime_config`, `evaluate_cutover_gate`
- `iceberg/writer/iceberg_writer.py` (full) — `load-id` idiom, `recover_pending`, `committed_load_records`, atomic `save_state`
- `iceberg/b2_spike.py` (full) — `collapse_delta`, `resolve_against_current`, FF-14
- `observability/postgres_exporter.py` (full), `observability/prometheus/alerts.yml` (full), `observability/grafana/dashboards/lakehouse-runtime.json` (all 8 targets extracted)
- `dags/lakehouse_maintenance.py` (`MAINTENANCE_TABLES`, `AUDIT_DDL`, upsert), `dags/warehouse_orders.py` (`marts/pipeline_runs`)
- `scripts/verify_m5_cutover.py`, `scripts/stack-reset.ps1`
- `docker-compose.extended.yml` (iceberg-writer, iceberg-medallion, observability-exporter, prometheus, grafana, volumes), `.env.example`, `pytest.ini`, `tests/conftest.py`

**Tests**
- `tests/test_ops.py`, `tests/test_observability.py`, `tests/test_m4_gold.py`, `tests/test_b2_medallion.py` (setup + outline)
- `tests/support/fakes.py`, `tests/support/b2_fakes.py`, `tests/support/medallion_harness.py`
- `tests/features/shadow_cutover.feature`, `tests/features/test_shadow_cutover.py`, `tests/features/gold_cutover.feature`, `tests/features/test_gold_cutover.py`
- `tests/e2e/test_lakehouse_e2e.py` (metric assertions), `tests/integration/test_m4_gold_cutover.py` (outline), `tests/test_medallion.py` (outline), `tests/test_m5_fitness_functions.py` (matrix assertions)

**PyIceberg 0.11.1 source (installed at `.venv/Lib/site-packages/pyiceberg/`)**
- `table/__init__.py:493, 531, 594-653, 1417-1496` — `append` / `overwrite` / `delete` signatures and property propagation
- `table/update/snapshot.py:239-341, 396-401, 521-547` — `_summary`, `_commit`, `_DeleteFiles` elision, `_FastAppendFiles`
- `table/snapshots.py:346-386` — `update_snapshot_summaries`
- Runtime signature inspection via `inspect.signature` against the installed 0.11.1

**Evidence artifacts**
- `artifacts/b2-rollout/06-o1-window.json` (all 10 rows parsed and paired), `06-o1-summary.json`, `06-telemetry-gate.json`, `06-bounded-workload.json`

**Repository policy and contracts**
- `AGENTS.md` (verification contract, runtime safety, documentation contract)
- `CLAUDE.md` (stateful boundary, B2 rollout state machine, dependency management, CI table)
- `docs/adr/0001-incremental-silver-and-gold.md:450-483` (D-4, verbatim)
- `docs/remediation/M5-fitness-functions-and-cutover-gates.md:25-90`
- `docs/observability/O1-runtime-observability.md` (full)
- `README.md:225-258`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md:136`, `docs/TESTING.md:15,179,196`, `docs/CONFIGURATION.md:74,76`
- `.github/workflows/ci-pr.yml:67`, `.github/workflows/ci-m5-gates.yml` (full)
- `.planning/ROADMAP.md:185-215`, `.planning/STATE.md`, `.planning/REQUIREMENTS.md` (full), `.planning/config.json`
- `.planning/quick/260816-docker-storage-investigation/260816-dsi-FINDINGS.md:141-145`

### Secondary (MEDIUM confidence)
- None. No web source was consulted; every claim in this document is grounded in repository or installed-package source.

### Tertiary (LOW confidence)
- None.

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|---|---|---|
| Gold provenance feasibility (Q1) | **HIGH** | Signature verified at runtime against the pinned version; propagation traced through three source files; the repo already does it on `overwrite` in production; a live run recorded the round-trip. Only the offline end-to-end probe is missing, and it is superseded. |
| Metric consumers (Q2) | **HIGH** | Exhaustive repo search; every consumer read directly. |
| Receipt placement (Q3) | **HIGH** for the facts (existing state, volumes, reset behaviour, precedents); **MEDIUM** for the recommendation, which is a judgement call the operator may weigh differently. |
| Test idioms (Q4) | **HIGH** for the idioms; **HIGH** for the harness break (deterministic from code); **MEDIUM** for the completeness of the "tests that will need updating" list — derived statically, not by running the suite. |
| Duration semantics (Q5) | **HIGH** for the current behaviour (traced line by line and confirmed against baseline data); **MEDIUM** for the recommendation. |
| Baseline evidence (Q6) | **HIGH** — recomputed from the artifact; matches CONTEXT exactly; pairing cross-checked arithmetically. |
| Validation architecture (Q7) | **HIGH** for framework/commands/existing layers; **MEDIUM** for the requirement→test mapping, which anticipates code that does not exist yet. |
| Security domain | **MEDIUM** — no new attack surface; the one genuinely security-relevant property (a forged receipt skipping a correctness gate) is identified and mitigated by design. |

**Research date:** 2026-08-17
**Valid until:** 2026-09-16 (30 days). All findings are grounded in pinned versions and repository source; they go stale only when this repository changes. Re-verify §4e and §4f if any test under `tests/features/` or `tests/support/` is modified before planning.
