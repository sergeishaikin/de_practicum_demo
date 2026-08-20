## Authorisation

Covered by the bounded Next Generation `ADOPT` programme recorded on 2026-08-19.
Second item of the programme, selected by re-reading the register and ADR-0003
after NG-0.9 archived: Wave 1, `ADOPT`, no hard dependency.

## Why

The platform already had useful identities — `cycle_id`, `load_id`, Iceberg
snapshot ids, Kafka offsets, Airflow run ids — and no contract binding them. Two
failure modes follow from that, and both are reachable today:

- a boundary **inventing** an identifier it does not have, which a later reader
  cannot distinguish from a real one;
- a per-execution identifier becoming a **Prometheus label**, which is unbounded
  in the dimension Prometheus charges for.

Prose cannot prevent either. Every subsequent NG item — lineage, telemetry,
catalog, evaluation provenance — names identifiers, so the vocabulary has to
exist before they do or each will invent its own.

## What Changes

- **`docs/PROVENANCE.md`** — the contract: the vocabulary and what each
  identifier is authoritative for, why identifiers are linked rather than merged,
  the never-fabricate rule, Iceberg snapshot as the version primitive (and why
  DVC/lakeFS are therefore not adopted), cardinality rules, data-plane/
  control-plane separation, and reproducibility rules.
- **`iceberg/common/provenance.py`** — the executable half. `CANONICAL_FIELDS`,
  `HIGH_CARDINALITY_FIELDS`, `FORBIDDEN_LABEL_NAMES`, a `ProvenanceEnvelope` that
  refuses to fabricate, and `cardinality_violations()`.
- **`tests/test_provenance_contract.py`** — 13 tests, including the negative test
  the item requires: every Prometheus metric declaration in the repository is
  parsed and checked for a high-cardinality label name.
- **`tests/integration/test_provenance_receipt.py`** — the end-to-end receipt,
  reading each hop back out of live state: Kafka position → `load_id` →
  Iceberg snapshot.
- **`AGENTS.md`** — a Provenance section pointing at both halves.

No runtime behaviour changes. The envelope is a contract for boundaries to adopt;
this change does not rewrite existing boundaries to emit it.

**Scope fence:**

- No existing processing boundary is rewritten to emit envelopes. That is
  per-boundary work, and doing it here would put an unreviewable behaviour change
  inside a contract change.
- No metric, label, schema or snapshot property changes. The contract describes
  what the platform already does and forbids what it already avoids.
- No new dependency, no new service, no Compose change.
- `git diff --exit-code dags/ dbt/ spark/ kafka/ observability/ scripts/ .planning/ docker-compose.yml docker-compose.extended.yml pyproject.toml uv.lock`
  SHALL be clean.
- Coverage threshold unchanged; no test weakened.

## Capabilities

### Modified Capabilities

None. The contract is documentation plus a library plus tests; it adds no rule
about how work is authorised or verified. `verification-contract` and
`engineering-governance` are untouched.

## Impact

- `docs/PROVENANCE.md` — new.
- `iceberg/common/provenance.py` — new, and in typed scope automatically.
- `tests/test_provenance_contract.py`, `tests/integration/test_provenance_receipt.py` — new.
- `AGENTS.md` — one section.
- `openspec/backlog/next-generation/00-INDEX.md` — NG-0.1's authorisation date.
