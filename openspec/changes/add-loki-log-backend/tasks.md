# Tasks: add-loki-log-backend

## Milestone 1 — recovery, design, preflight (authorised)

- [x] Verify merged baseline, branch, worktree and clean status.
- [x] Promote NG-0.6 to `ACTIVE` with explicit Milestone 1 authorisation.
- [x] Revalidate Loki release, image manifest and native OTLP route against
      primary documentation.
- [x] Inventory first-party logging surfaces and classify collection scope.
- [x] Define schema, labels, structured metadata, correlation, redaction,
      storage/retention, failure, resource and CI contracts.
- [x] Record preflight limits and evidence in `evidence.md`.
- [x] Create the required OpenSpec capability delta.

## Milestone 2 — implementation (not authorised)

- [ ] Add pinned Loki profile and isolated storage configuration.
- [ ] Configure Collector `otlphttp` Loki exporter and bounded queue/WAL
      behaviour without changing the existing trace/metrics routes.
- [ ] Adapt first-party log emitters to the approved schema and redaction.
- [ ] Provision Grafana Loki datasource and trace-to-logs derived fields.
- [ ] Add capability tests, failure injection, resource/cardinality receipts,
      and a separate CI workflow; keep core H1 Loki-free.
- [ ] Obtain explicit Milestone 2 authorisation before executing any item above.
