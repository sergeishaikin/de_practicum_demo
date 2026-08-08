# M5 — Fitness functions, CI gates, cutover evidence, and observability

Status: **implementation complete**.

M5 binds the accepted M1–M4 architecture to executable tests and an operational decision
procedure. It does not redesign the data path, remove the legacy rollback path, or implement
D-3a physical layout tuning.

## Fitness-function matrix

| ID | Protected decision / invariant | Executable evidence | Execution tier | Blocking |
| --- | --- | --- | --- | --- |
| FF-04 / TE-FF-ORDER | business_version, never kafka_offset, orders current state | M5 contract and B2 resolver tests | PR fast | yes |
| FF-09 / TE-FF-UNIQUE | Silver has one current row globally per order_id, including cross-date updates | M5 contract and M3/M4 live tests | PR live + main/nightly | yes |
| FF-14 / TE-FF-VERSION-CONFLICT | Equal business version with a different payload is surfaced before mutation | B2 resolver and medallion tests | PR fast | yes |
| FF-07 / TE-FF-COMMIT | Only Spark-committed landing files are Bronze-eligible | writer discovery and crash tests | PR fast + PR live | yes |
| FF-05 / TE-FF-RECOVER | Crash before/after Silver commit converges without loss or double-apply | M3 recovery and writer crash suites | PR live + main/nightly | yes |
| FF-06 / TE-FF-PERSIST | persisted-Silver Gold does not rebuild from an in-memory B2 frame | M4 unit and live cutover tests | PR fast + PR live | yes |
| M4-SHADOW / ADR X-6 | Legacy and B2 logical state is equal by order_id; transport metadata is excluded | comparator and M4 shadow tests | PR fast + cutover | yes |
| FF-01 / TE-FF-EQUIV | Incremental state remains equivalent to the accepted logical projection | M4 shadow evidence; pinned-snapshot expansion remains available | cutover/main | yes |
| FF-02 / TE-FF-SCAN | Physical locality evidence is recorded without becoming a correctness threshold | SPIKE-2 JSON and baseline document | main/nightly | no |
| FF-08 / TE-FF-SCHEMA | business_version survives the producer → Spark → Bronze → Silver contract | order contract tests | PR fast | yes |
| FF-10 / TE-FF-RETENTION | Maintenance retention does not undercut recovery evidence | `dags/recovery_contract.py` import-time assertion | unit test + Airflow DAG import | yes |
| FF-11 / TE-FF-ATOMIC | Writer and medallion control writes are recoverable | writer state and M3 progress tests | PR live + main/nightly | yes |
| FF-13 / TE-FF-KEYING | Producer keeps order_id Kafka key for locality; this is not Silver correctness | producer contract test | PR fast | no |

The strict SPIKE-1 expected-failure test remains in
tests/integration/test_trino_merge_interop.py. Its xfail(strict=True) is intentional: if the
pinned PyIceberg/PyArrow reader ever starts consuming Trino position deletes, the test becomes an
unexpected pass and forces review of ADR-0001 D-3.

## Runtime observability

marts.lakehouse_metrics remains the operational sink. Its schema is extended additively and
existing deployments are upgraded with ALTER TABLE ... ADD COLUMN IF NOT EXISTS. M5 records:

~~~text
work_available, work_in_flight, work_completed
keys_processed, lower_versions_ignored, ff14_conflicts
shadow_comparisons, shadow_mismatches
silver_duration_ms, gold_duration_ms
files_planned, bytes_planned
files_removed, files_added, bytes_removed, bytes_added
snapshot_delta
~~~

The B2 cycle records work-state counts, affected keys, ignored lower versions, FF-14 failures,
processed files, and Silver duration. M4 records shadow success/failure and separate Silver/Gold
durations. SPIKE-2 remains the source of physical plan/read/write evidence:
files_planned_for_read, bytes_planned_for_read, data_files_removed, data_files_added,
bytes_removed, bytes_added, and snapshot_count_delta.

Useful queries:

~~~sql
select source, status, sum(work_in_flight), sum(ff14_conflicts),
       sum(shadow_comparisons), sum(shadow_mismatches)
from marts.lakehouse_metrics
group by source, status;

select metric_ts, source, status, keys_processed,
       lower_versions_ignored, silver_duration_ms, gold_duration_ms
from marts.lakehouse_metrics
order by metric_ts desc
limit 20;
~~~

Metrics remain best-effort: a metrics database outage is logged and does not change the
Bronze/Silver commit protocol.

## Operational cutover gate

The only accepted target configuration is:

~~~text
SILVER_MODE=b2
GOLD_SOURCE=persisted_silver
SHADOW_COMPARE=1
~~~

The pure evaluator in iceberg/common/cutover.py requires this objective evidence:

~~~text
shadow_comparison_success = true
unresolved_progress = 0
ff14_conflicts = 0
recent_recovery_tests_passed = true
gold_equivalence = true
rollback_verified = true
~~~

Evaluate an evidence bundle with:

~~~powershell
$env:SILVER_MODE = "b2"
$env:GOLD_SOURCE = "persisted_silver"
$env:SHADOW_COMPARE = "1"
python scripts/verify_m5_cutover.py --evidence artifacts/m5/cutover-evidence.json
~~~

The command exits non-zero on any failed check. Human review may inspect the evidence, but cannot
turn a failed check into a pass by acknowledgement alone.

### Checklist

1. Run the PR fast and live gates.
2. Verify recent M3 before/after-commit recovery evidence is green.
3. Verify M4 shadow comparison and exact logical Gold equivalence.
4. Require zero unresolved progress work entries.
5. Require zero FF-14 conflicts for the release window.
6. Verify b2/persisted_silver/shadow configuration in the deployed environment.
7. Verify legacy rollback without a Silver or progress reset.
8. Run the cutover evaluator against the collected evidence bundle.

### Rollback

Rollback is required when shadow comparison fails, progress remains unresolved, FF-14 appears,
Gold equivalence is lost, or recovery evidence is stale/missing. Set:

~~~text
GOLD_SOURCE=legacy
~~~

Keep SILVER_MODE=b2 when B2 Silver remains healthy; this rolls back only the Gold source. If B2
Silver itself is unhealthy, switch SILVER_MODE=legacy as the broader emergency rollback. Do not
delete progress, recreate completed outbox records, or reset Iceberg tables.

## CI placement

The existing ci-pr.yml remains the fast PR gate for Ruff, Black, schema/domain contracts, M5 unit
contracts, and coverage. The new .github/workflows/ci-m5-gates.yml starts only MinIO and the
Iceberg REST catalog on pull requests and runs the stable writer crash, M3 recovery, and M4
cutover tests. Core stateful correctness is therefore checked before merge.

The existing ci-integration.yml remains the broader live Iceberg/Trino suite on main/manual
execution. ci-nightly.yml remains responsible for the full integration layer, deterministic
Kafka/Spark E2E, and maintenance verification. SPIKE-2 locality measurement remains non-blocking
evidence.

## Verification evidence

M5 verification commands:

~~~text
ruff check .
python -m pytest -q --basetemp .pytest-m5-fast
python -m pytest -q -m integration tests/integration/test_crash_recovery.py tests/integration/test_m3_b2_recovery.py tests/integration/test_m4_gold_cutover.py
python -m pytest -q -m e2e tests/e2e/test_lakehouse_e2e.py -s
~~~

Observed local evidence:

~~~text
ruff check .                                      All checks passed
fast suite                                        82 passed, 28 deselected
M3 live recovery                                  1 passed in 23.13s
writer crash recovery                             2 passed in 20.16s
M4 live cutover/rollback                          1 passed in 13.70s
compose config --quiet                            passed
verify_m5_cutover.py example evidence             passed
deterministic E2E                                 1 passed in 111.72s
~~~

The PR live command is executed by ci-m5-gates.yml against the minimal live stack; the E2E command
remains the nightly gate. Existing assertions are not weakened for M5.

## Residual risks and explicit deferrals

- The evaluator validates an evidence bundle; production evidence collection and alert routing
  remain operational work.
- Shadow comparison is a full logical-state scan and may be too expensive at larger scale.
- Gold remains a full overwrite and can create snapshot churn for a logical no-op.
- One active medallion processor per progress path is still assumed.
- Retention/recovery policy needs an environment-specific operational value before production.
- M5 introduces no Prometheus, Grafana, or new observability platform.
- D-3a bucket/file-sizing/compaction tuning remains explicitly deferred and non-blocking.
