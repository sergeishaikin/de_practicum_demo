## Authorisation

Explicit ancillary authorisation inside the bounded Next Generation programme,
granted 2026-08-20 as programme-support work. Not an NG backlog item and not
added to the register. The programme resumes automatically on archive.

## Why

The repository let an agent read **"Docker Desktop is installed but currently
stopped"** as **"live dependencies are unavailable"**, and that inference was
made. `AGENTS.md` said to run live markers "when their dependencies are
available" without defining availability, so an idle daemon looked like an
absent one.

This is not hypothetical. NG-0.1's archived evidence claimed its provenance
receipt "could not run locally — no live catalog or object store here". Docker
Desktop was installed and running throughout. The receipt was never attempted.
It now runs locally in **2.07 seconds**.

The cost is not only a false statement. Every live check deferred to CI is a
20-minute round trip instead of a 30-second one, and this change found that out
the hard way: NG-0.2's Airflow probe failed in CI on an API mismatch, and was
diagnosed and fixed locally in about two minutes once Docker was actually used.

## What Changes

- **`docs/LOCAL-ENVIRONMENT.md`** — new. Two deliberately separated halves: a
  normative execution contract, and a dated measured snapshot labelled as
  evidence rather than as a guarantee.
- **`AGENTS.md`** — a normative *Local runtime availability* section, and the
  two places that said "when dependencies are available" now say what that
  means.
- **`docs/DEVELOPMENT.md`** — a *Container runtime* section: engine readiness
  versus CLI presence, the startup procedure, and how to enumerate services and
  images mechanically.
- **`docs/TESTING.md`** — a *Local-first live verification policy* and a
  marker-to-runtime-surface table derived from the actual tests and Compose.
- **`scripts/local_runtime_inventory.py`** — new, read-only. Reports host,
  Docker readiness and resource envelope, the Compose graph, running containers
  and image-pin drift between `.env` and `.env.example`. Optional JSON output.
- **`tests/test_local_runtime_inventory.py`** — 13 tests, including that a
  stopped engine is reported rather than raised, that only `*_IMAGE` keys are
  read from env files, and that the contract sentences are still present in all
  four documents.
- **`openspec/changes/archive/2026-08-20-add-platform-provenance-contract/evidence.md`**
  — a dated correction of the false locality claim. Corrected in place rather
  than deleted, because the reasoning error is the part worth keeping visible.

**Scope fence:**

- No production code changes. No `iceberg/`, `dags/`, `dbt/`, `spark/`,
  `kafka/`, `observability/` change.
- No dependency, image, Compose or CI workflow change.
- The developer's local `.env` is **not** rewritten. Its floating image tags are
  reported, not corrected: an uncommitted file belongs to the developer.
- The generated inventory under `artifacts/` is evidence and stays untracked.
- No test weakened; coverage threshold unchanged.

## Capabilities

### Modified Capabilities

- **`verification-contract`** — what "available" means for a dependency, when
  local verification is required relative to CI, and that environment facts are
  measured rather than asserted.

## Impact

- `docs/LOCAL-ENVIRONMENT.md`, `scripts/local_runtime_inventory.py`,
  `tests/test_local_runtime_inventory.py` — new.
- `AGENTS.md`, `docs/DEVELOPMENT.md`, `docs/TESTING.md` — extended.
- NG-0.1's archived evidence — corrected.
- `tests/integration/test_airflow_lineage_provider.py` — the NG-0.2 probe fixed
  using this change's own procedure, and verified locally before pushing.
