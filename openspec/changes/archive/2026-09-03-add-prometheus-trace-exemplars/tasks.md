# Tasks

- [x] Create isolated worktree/branch from NG‑0.5 checkpoint `30e7debe`.
- [x] Inspect existing metrics, OTel context boundary and pinned images.
- [x] Implement sampled current-trace exemplar helper and fail-open metric
      observation on existing `lakehouse_duration_seconds`.
- [x] Keep trace ID out of labels and PostgreSQL durable metrics; add regression
      and focused exemplar tests.
- [x] Enable bounded Prometheus exemplar storage and explicit OpenMetrics
      scrape negotiation.
- [x] Clarify standing observability contract without weakening cardinality or
      spanmetrics lockout.
- [x] Prove OpenMetrics output in the pinned application image.
- [x] Prove Prometheus scrape/target health and exemplar retrieval through its
      API on an isolated temporary network.
- [x] Run final full repository gates and archive this change. A short NG‑0.5
      M1R reference remains intentionally separate; NG‑0.5 stays blocked.
