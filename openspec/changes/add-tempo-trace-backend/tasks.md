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
- [ ] Milestone 2 implementation (explicitly blocked; requires a new grant and
      resolved exemplar governance).
