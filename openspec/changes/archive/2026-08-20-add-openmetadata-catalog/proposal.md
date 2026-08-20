## Authorisation

Covered by the bounded Next Generation `ADOPT` programme. Fourth item, selected
by re-reading the register and ADR-0003 after NG-0.2 archived: NG-0.3, Wave 3,
`ADOPT`, hard dependencies NG-0.1 and NG-0.2 both `DONE`.

## Why

The platform now emits runtime lineage and has an identity vocabulary, and
neither has a consumer. NG-0.2 writes newline-delimited JSON to a shared volume:
enough to prove the graph exists, useless as an operational surface — no search,
no retention, no impact analysis, no ownership.

NG-0.3 makes the metadata a product: one place to answer "what is this dataset,
who owns it, what feeds it, and what breaks if I change it".

## OM-PREFLIGHT first

ADR-0003 requires this change to open with a fail-fast gate rather than a build,
because NG-0.3 is the most expensive item in the package and its own spec names
DataHub as the fallback — an unmet connector assumption means redoing an XL
item. The gate proves, against the pinned candidate and this repository:

```text
Airflow coverage · dbt artifacts · Kafka metadata · Trino/Iceberg visibility
required lineage edges · required column-lineage subset · OpenLineage ingestion
auth and secrets model · clean start · measured resource envelope
```

`PASS` continues into the full implementation. `FAIL` stops before the expensive
integration, classifies the gap, and evaluates DataHub only if the blocker is
material.

## What Changes (proposal-time intent)

At proposal time, scope was to be decided by the preflight result and recorded
in `design.md` before any integration work. In outline:

- **An opt-in `metadata` Compose profile.** OpenMetadata, OpenSearch and a
  dedicated metadata database, none of which join the core stack. `docker
  compose` without the profile keeps current behaviour exactly.
- **Runtime lineage repointed, not rewritten.** NG-0.2's emitters change
  transport by configuration — `OPENLINEAGE__TRANSPORT__TYPE` from `file` to
  `kafka` — which is the portability property NG-0.2 was designed for.
- **Connector coverage as an explicit inventory**, supported and unsupported
  alike. An asset the connectors cannot reach is listed as a gap, never omitted
  from a claimed end-to-end graph.
- **Ownership and domains as code**, not hand-entered in a local UI.
- **Evidence**: clean profile start from fresh volumes, a real lineage path,
  a destroy-and-rebuild proof, and a measured resource receipt.

**Scope fence:**

- No metadata write path into canonical Iceberg, `dwh` business tables or Kafka
  business topics. The catalog is a consumer of data-plane state.
- No second Airflow. No replacement of Airflow, dbt or Grafana.
- No DataHub deployment unless the preflight classifies a material blocker.
- The core stack's resource envelope does not increase: the profile is opt-in,
  and `git diff --exit-code` on the core service definitions stays clean apart
  from profile assignment.
- No change to medallion, writer or streaming processing semantics.
- Coverage threshold unchanged; no test weakened.

## Capabilities

### Modified Capabilities

- **`runtime-lineage`** — where emitted lineage is delivered, and the rule that
  a catalog may not become a second authority for an edge the runtime already
  owns.

## Impact (proposal-time forecast)

At proposal time, this was to be finalised by the preflight. Expected paths
were `docker-compose.extended.yml`
(profile), `iceberg/requirements.in` (Kafka transport dependency),
`docs/CATALOG.md`, connector configuration as code, and tests covering the
coverage inventory and the control-plane-outage rule.

## Reconciliation note

This proposal records the original Milestone 2 decision boundary and is kept
as historical design context. The operator accepted the preflight and later
explicitly authorised Milestone 3 continuation. Implementation and local
acceptance subsequently completed through `04f0402`, including the
metadata-side object-store Container compatibility adapter. The final current
design, execution tasks, evidence, and standing capability delta are recorded
in the reconciled sections/files in this active change; this note does not
rewrite the proposal's earlier planning sequence.
