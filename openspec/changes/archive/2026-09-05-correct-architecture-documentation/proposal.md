# Proposal: correct-architecture-documentation

## Problem

`README.md`'s architecture section describes an earlier version of this
platform. Four defects, each verified against the repository rather than read
off the page.

- **It asserts an edge that does not exist.** The hero diagram draws
  `Airflow → Spark Connect` as though orchestration depended on it. No DAG in
  `dags/` references Spark or Spark Connect at all — they talk to PostgreSQL
  and Trino — and `spark-connect` is `profiles: ["tools"]`, an optional
  interactive endpoint. The diagram makes a development tool look like a core
  dependency.
- **It presents one medallion mode as the only one.** The Iceberg section says
  the medallion "rebuilds `silver.orders_clean` … and `gold.orders_daily_metrics`
  … from bronze every 60 seconds", never mentioning that this is one of four
  validated rollout modes. It then documents `files_planned`, `snapshot_delta`,
  `shadow_skipped` and `gold_skipped` — columns only the incremental `b2` path
  populates — without saying they stay empty in the mode it described.
- **It misrepresents the Iceberg relationship.** The diagram draws
  `MinIO → Iceberg REST Catalog → Trino` as a data path, and the prose says the
  catalog is "backed by MinIO" immediately before saying its state is in
  SQLite. The catalog holds metadata; MinIO holds data files; the catalog is
  not a stage between them.
- **Its profile table is incomplete.** Compose declares six profiles. The table
  listed four. The two it omitted — `otel` and `observability-next` — are named
  in the README's own instructions twelve lines earlier, so a reader is told to
  use profiles the table says do not exist.

The first and last are the ones that mislead rather than merely age: one
invents an architectural dependency, the other makes the deployment topology
unreconstructable from the document that is supposed to carry it.

## Proposed bounded change

Restructure the architecture section into the planes the platform actually has
— streaming lakehouse, batch warehouse, Iceberg catalog and query, governance,
observability, and developer tools — with each optional plane labelled by the
profile that starts it. Correct the Iceberg relationship. Document all six
profiles. Add a *Medallion rollout modes* section stating the validated matrix
and which mode ships.

Add one structural fitness check: the profile table must name exactly the
profiles Compose declares.

## Non-goals

- No runtime, Compose, dbt, Airflow or observability change. This change edits
  documentation and adds one test.
- No rewrite of `docs/ARCHITECTURE.md`. Its mermaid diagrams were already
  correct and already plane-separated; it needed one sentence, naming which
  rollout mode ships.
- No snapshot testing of prose. The one check added asserts a set equality
  between two machine-readable facts. Descriptive paragraphs stay prose.

## A correction to the brief

The task described the "rebuilds Silver and Gold every 60 seconds" wording as
stale, to be replaced with the incremental B2 behaviour. Measured against the
repository, that is backwards: `docker-compose.extended.yml` ships
`SILVER_MODE=${SILVER_MODE:-legacy}` and `.env.example` ships
`SILVER_MODE=legacy`, `GOLD_SOURCE=legacy`, `SHADOW_COMPARE=0`. A stack started
from the committed configuration **does** rebuild both layers in full every
cycle. The sentence was accurate; what was missing was that it describes one
mode of four, and that the B2-only metric columns documented later belong to a
mode the reader has not been told exists.

Replacing it with an unconditional description of incremental B2 would have
introduced a new defect in the course of fixing an old one. Both modes are
documented instead, with the default named.

## Scope fence

- This change SHALL NOT alter `SILVER_MODE`, `GOLD_SOURCE`, `SHADOW_COMPARE` or
  any other shipped default. The mismatch between the committed default
  (`legacy`) and the runtime state recorded in
  `artifacts/b2-rollout/07-rollout-result.md` (`cutover`) is a configuration
  question, not a documentation one, and is recorded for the backlog rather
  than resolved here.
- This change SHALL NOT add fitness checks over descriptive prose.
