# Evidence: add-grafana-correlation-slo M1

## Recovery

| Check | Result |
|---|---|
| Baseline branch | `test/dbt-extensive-testing` |
| Baseline SHA | `d031679de39006f14493fd178ac0b9ff32919498` |
| Remote SHA | verified equal to baseline |
| Consolidation H1 | GitHub Actions `33908268598`, exact SHA, both jobs successful |
| Worktree | dedicated `ng07-correlation`, clean at start |
| Scope | research/design/preflight only; no runtime files changed |

## Repository inventory

- Dashboard: `observability/grafana/dashboards/lakehouse-runtime.json`, UID
  `lakehouse-runtime`, 11 panels including four row sections and seven
  time-series panels; no variables, data links or annotations.
- Dashboard provider: file-backed, `editable: false`, `disableDeletion: true`.
- Datasources: provisioned Prometheus (`uid: prometheus`), Tempo
  (`uid: tempo`) and Loki (`uid: loki`), all `editable: false`.
- Correlation already present: Prometheus exemplar destination to Tempo, Tempo
  `tracesToLogsV2` to Loki, Loki `trace_id` derived field to Tempo.
- Prometheus rules: five existing repository-managed alerts in
  `observability/prometheus/alerts.yml`; no Grafana-managed alert rules.
- Durable authority: PostgreSQL `marts.lakehouse_metrics` and
  `marts.maintenance_runs`; only cycle envelope rows reach Prometheus.
- OpenMetadata known FQNs: `lakehouse_trino.iceberg.bronze.orders`,
  `lakehouse_trino.iceberg.silver.orders_clean`,
  `lakehouse_trino.iceberg.gold.orders_daily_metrics`.

## Version probes and primary sources

Local read-only image probes against repository-pinned digests reported:

- Grafana `11.2.0`;
- Prometheus `3.5.0`;
- Tempo `v3.0.3`;
- Loki `3.7.7`;
- OpenTelemetry Collector Contrib `0.157.0`;
- OpenMetadata server/ingestion `1.13.3` as recorded by adopted NG-0.3
  evidence for the pinned digests.

Primary documentation revalidated on 2026-09-04:

- Grafana provisioning: <https://grafana.com/docs/grafana/latest/administration/provisioning/>.
- Grafana data links: <https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/configure-data-links/>.
- Grafana trace-to-logs (Tempo/Loki both directions and low-cardinality guidance): <https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/>.
- Grafana trace correlations: <https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/trace-correlations/>.
- OpenMetadata API URI and `href` conventions: <https://docs.open-metadata.org/v1.12.x/api-reference/main-concepts/metadata-standard/apis>.
- OpenMetadata FQN semantics: <https://docs.open-metadata.org/v1.12.x/api-reference/main-concepts/backend-db>.
- OpenMetadata lineage API and downstream graph: <https://docs.open-metadata.org/v1.12.x/api-reference/lineage/add>.
- OpenMetadata custom properties/entity references: <https://openmetadatastandards.org/schemas/type/custom-properties/>.

## Preflight classification

`PASS_WITH_EXPLICIT_LIMITATIONS`.

Verified: repository provisioning model, stable datasource/dashboard UIDs,
Prometheus exemplar-to-Tempo configuration, bidirectional Tempo/Loki
correlation primitives, low-cardinality design constraints, deterministic
OpenMetadata FQNs/API `href`, lineage graph API, and all pinned image versions.

Limitations: the current dashboard has no links/variables/SLI presentation;
the shadow-mismatch counter has no exemplar and therefore needs a degraded
metric-only branch; OpenMetadata UI-route stability and reproducible reverse
OpenMetadata-to-Grafana links are not proven; missing-arrival and metadata
freshness require new signals; no end-to-end latency timestamp exists for all
candidate operations. These are design constraints, not implementation work in
M1.

## Validation receipts

The M1-only validation to run before commit is:

```text
openspec validate --all --strict
uv run --locked python openspec/backlog/validate_backlog.py
git diff --check
```

No dashboard, alert, datasource, OpenMetadata or live-stack mutation is part of
this milestone.
