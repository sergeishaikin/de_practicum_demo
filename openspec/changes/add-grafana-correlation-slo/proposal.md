# Proposal: add-grafana-correlation-slo

## Milestone 1 boundary

This authorised milestone recovers the exact consolidated baseline, inventories
the existing Grafana/Prometheus/Tempo/Loki/OpenMetadata surfaces, revalidates
current product capabilities against primary documentation, and records an
implementation-ready correlation, SLI/SLO and acceptance design. It does not
change runtime, dashboards, alert rules, datasources, instrumentation, or
OpenMetadata configuration.

## Problem

The repository already has provisioned Grafana, Prometheus, Tempo and Loki
surfaces, but no tested operational path connects an authoritative symptom to
the exact trace, logs, execution identity, dataset and downstream impact. The
current dashboard is useful for metrics but has no variables, links or SLI
dictionary. Missing-arrival detection is also not represented and must not be
mislabelled as dbt freshness.

## Proposed bounded change

Evolve the existing `lakehouse-runtime` dashboard and its repository-backed
provisioning with bounded cross-links and explicitly classified SLIs. Reuse the
adopted Prometheus exemplar, Tempo-to-Loki and Loki-to-Tempo contracts. Link a
known dataset to its deterministic OpenMetadata FQN without duplicating the
catalog or lineage UI. Candidate alerts remain evidence-gated and all new SLO
numbers remain provisional until measured.

## Scope fence

- M1 is research/design/preflight only; no executable implementation.
- No new metrics, instrumentation, recording rules, dashboard JSON, alerts or
  datasource edits.
- No Grafana/Tempo/Loki/Collector/OpenMetadata runtime changes.
- No custom portal, embedded catalog, high-cardinality labels or IDs as index
  dimensions.
- No production SLO threshold adoption and no NG-0.8 work.

## Preflight classification

`PASS_WITH_EXPLICIT_LIMITATIONS`: the pinned Grafana 11.2.0, Prometheus 3.5.0,
Tempo 3.0.3, Loki 3.7.7 and Collector 0.157.0 images expose the required
provisioning/correlation primitives. The repository's OpenMetadata 1.13.3
profile provides deterministic FQNs, API `href` and lineage, but a reproducible
reverse OpenMetadata-to-Grafana link is not demonstrated by the current
contract and remains a bounded limitation. Missing-arrival and several latency
SLIs require signals not present in the baseline.

Implementation may be considered only after an independent M1 review and a
separate explicit M2 authorization.
