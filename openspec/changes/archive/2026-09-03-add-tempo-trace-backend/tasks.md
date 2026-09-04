# Milestone 1 tasks

- [x] Recover `feature/ng-0.5-tempo` onto adopted NG-0.4 closure and verify a
      clean worktree and no unique old NG-0.5 governed work.
- [x] Promote only NG-0.5 to `ACTIVE/pending` with explicit M1 provenance.
- [x] Inspect current Collector extension point, Prometheus scrape/metric
      authority, Grafana provisioning, MinIO/Iceberg prefixes and core profile.
- [x] Revalidate Tempo deployment modes, OTLP ingestion, TraceQL, S3-compatible
      storage, retention/compaction, metrics-generator and Grafana correlations
      against primary sources.
- [x] Search for existing Prometheus exemplar emission/configuration and record
      the result without changing metrics.
- [x] Define topology, ownership, storage isolation, retention, identity,
      redaction, failure-injection, resource and future CI contracts.
- [x] Record the exemplar contradiction and the two smallest governance
      resolutions; do not implement either resolution.
- [x] M1R: reference archived bounded application exemplars and verify that the
      metric-to-trace contradiction is resolved without span-derived metrics.

## Milestone 2 — bounded implementation and acceptance (2026-09-03)

- [x] Revalidate Tempo v3.0.3 release and pin the verified multi-arch image
      digest; validate the rendered Tempo 3.x configuration with `--config.verify`.
- [x] Add the opt-in `observability-next` profile with separate Tempo WAL/data
      and MinIO trace storage, credentials, bucket prefix, retention and
      compaction controls.
- [x] Route Collector traces through the existing `telemetry-backend` boundary
      with bounded queue/retry settings; retain OTLP application destination and
      the Prometheus/Grafana metrics authority.
- [x] Provision deterministic Grafana Tempo and Prometheus datasource UIDs,
      trace-to-metrics and exemplar trace destinations; leave Loki unconfigured.
- [x] Run focused contract tests, the existing NG-0.4 acceptance harness and
      the bounded Tempo live acceptance (OTLP, TraceQL, exemplar same-trace ID).
- [x] Define capability CI as an optional workflow; collect resource, outage,
      restart, object-store isolation and canonical-parity receipts.
- [x] Milestone 2 final report and explicit user approval for archive/adoption.

## M2B — closure blockers only

- [x] Add trace redaction to the traces pipeline and run a forbidden-value
      regression with useful load identity preserved.
- [x] Execute Tempo-vs-canonical MinIO permission proof (ALLOW dedicated trace
      prefix, DENY canonical namespace).
- [x] Start Grafana with real provisioning and verify same-trace proxy results
      for Tempo and Prometheus exemplar navigation.
- [x] Add Tempo stop/restart and object-store stop/restart probes to capability
      CI; keep canonical H1 as a separate required workflow.
- [x] Verify the configured completion gate `uv run --locked mypy` passes.
- [x] Obtain exact-SHA green core H1 receipt before final adoption/archive.

## M2C — verification repair (2026-09-03)

- [x] Pass actual Tempo credentials to both storage probes without logging
      secrets; assert positive `returncode == 0` and negative `returncode != 0`.
- [x] Record a pre-fix traces-pipeline regression with forbidden bearer,
      password and SQL values retained in Tempo.
- [x] Assert the repaired traces pipeline masks all forbidden values while
      preserving the safe load identity.
- [x] Run capability CI on the repaired implementation SHA.
- [x] Repeat exact-SHA core H1 because the Collector redaction policy changed.
