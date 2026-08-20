## Milestone 1 — recovery, design and preflight (authorised)

- [x] 1.1 Verify branch, commit, clean worktree and existing OpenSpec state.
- [x] 1.2 Promote NG-0.4 to `ACTIVE` and create this change directory.
- [x] 1.3 Inventory current Prometheus/Grafana metrics, Compose services,
      Kafka client version and existing OTel transitive dependencies.
- [x] 1.4 Revalidate OTLP exporter, Collector resiliency/WAL and Kafka semantic
      convention assumptions against primary OpenTelemetry documentation.
- [x] 1.5 Run bounded read-only Docker/Compose/resource probes and record their
      results in `evidence.md`.
- [x] 1.6 Define instrumentation, context, redaction, sampling, queue/retry/WAL,
      failure-injection, resource and CI contracts.
- [x] 1.7 Add the required `observability-telemetry` specification delta.
- [x] 1.7A Freeze the official Contrib distribution/image family, component
      allow-list, OTLP/gRPC network contract and immutable-digest requirement.
- [x] 1.7B Freeze Collector-only backend exporter insertion through the named
      `telemetry-backend` slot; prohibit direct app backends and spanmetrics.
- [x] 1.7C Freeze Prometheus/PostgreSQL metric authority and the span-derived
      metric lockout; record the decision in `design.md` and `evidence.md`.
- [ ] 1.8 Obtain operator acceptance of the Milestone 1 report.

## Milestone 2 — implementation (not authorised)

- [ ] 2.1 Pin Collector distribution/image, OTel SDK/exporter packages and
      messaging semantic-convention mode; regenerate locked dependency files.
- [ ] 2.2 Add the opt-in Collector profile, health/readiness, Prometheus
      self-metrics and bounded persistent storage with least privilege.
- [ ] 2.3 Instrument writer, medallion and the work-performing observability
      exporter with fail-open OTLP traces/logs and stable resources.
- [ ] 2.4 Implement and test Kafka W3C propagation with `confluent-kafka`.
- [ ] 2.5 Implement redaction, bounded attributes and explicit sampling policy.
- [ ] 2.6 Execute outage, retry, queue overflow, Collector restart/WAL and
      recovery-drain failure-injection tests; prove canonical output parity.
- [ ] 2.7 Measure CPU/RSS/disk/throughput overhead and update dashboards/alerts
      without changing existing Prometheus/Grafana ownership.
- [ ] 2.8 Run focused tests, Compose config, clean-start profile and existing
      Prometheus/Grafana gates; archive only after all acceptance evidence is
      complete.
