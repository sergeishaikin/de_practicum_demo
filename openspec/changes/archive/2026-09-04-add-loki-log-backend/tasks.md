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

## Milestone 2 — implementation (authorised)

- [x] Add pinned Loki profile and isolated storage configuration.
- [x] Configure Collector `otlphttp` Loki exporter and bounded queue/WAL
      behaviour without changing the existing trace/metrics routes.
- [x] Adapt the adopted first-party emitters (Iceberg writer, medallion and
      observability exporter) to the approved schema and redaction; Kafka,
      Spark and Airflow remain explicitly out of scope for this first wave.
- [x] Provision Grafana Loki datasource and trace-to-logs derived fields.
- [x] Add capability tests, failure injection, resource/cardinality receipts,
      and a separate CI workflow; keep core H1 Loki-free.
- [x] Obtain explicit Milestone 2 authorisation before executing implementation.

## Milestone 2B — closure blockers (authorised)

- [x] Add exact `event.name`/severity fields and verify adopted-scope records.
- [x] Expand persisted redaction regression and demonstrate pre-fix failure.
- [x] Prove Loki, canonical MinIO and Tempo storage isolation with return codes.
- [x] Execute Grafana proxy same-trace queries in the live harness and CI.
- [x] Execute canonical healthy/outage parity and Loki/object-store recovery.
- [x] Execute log-path Collector failure, bounded queue and restart evidence.
- [x] Record indexed-label/cardinality, object-store, latency and resource receipts.
- [x] Run exact-SHA capability CI and Loki-free H1; keep lifecycle ACTIVE/pending.

## Milestone 2C — persistent queue / WAL closure (authorised)

- [x] Bind the Loki exporter queue to the existing `file_storage` extension.
- [x] Validate Collector v0.157.0 configuration and volume ownership.
- [x] Demonstrate WAL growth, hard Collector restart and post-restore recovery.
- [x] Exercise bounded near-capacity queue pressure with canonical work intact.
- [x] Rename the single LogQL latency receipt honestly (no fake p95 claim).
- [x] Run new exact-SHA capability CI and Loki-free H1; keep lifecycle ACTIVE/pending.

## Final adoption and archive (authorised)

- [x] Reconcile the adopted contract into `openspec/specs/loki-log-backend`.
- [x] Reconcile NG-0.6 lifecycle to `DONE / ADOPTED` while preserving its
      authorization history and leaving NG-0.7 `PLANNED / pending / none`.
- [x] Archive this completed change under the dated archive path.
- [x] Run final post-archive capability, H1, Core CI and M5 receipts on the
      exact closure SHA.
