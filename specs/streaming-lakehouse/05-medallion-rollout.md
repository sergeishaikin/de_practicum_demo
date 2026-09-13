# Layer 5 — Medallion Rollout State Machine

Runtime behavior is selected by the validated tuple:

```text
(SILVER_MODE, GOLD_SOURCE, SHADOW_COMPARE)
```

Invalid combinations fail validation rather than starting with an undefined mode.

## Allowed states

| Mode | `SILVER_MODE` | `GOLD_SOURCE` | `SHADOW_COMPARE` | Effective behavior |
|---|---|---|---:|---|
| legacy | `legacy` | `legacy` | 0 | Full Silver rebuild, then full Gold rebuild |
| rollback | `b2` | `legacy` | 0 | Incremental Silver, Gold still follows legacy path |
| shadow | `b2` | `legacy` | 1 | Incremental Silver plus legacy candidate comparison |
| cutover | `b2` | `persisted_silver` | 1 | Persisted incremental Silver becomes Gold source with shadow validation |

The shipped default is:

```text
legacy / legacy / 0
```

## State-oriented view

```text
legacy
  -> FullSilverRebuild
  -> FullGoldRebuild

rollback
  -> IncrementalSilver
  -> LegacyGold

shadow
  -> IncrementalSilver
  -> BuildLegacyCandidate
  -> Compare
  -> certify passing comparison

cutover
  -> IncrementalSilver
  -> ShadowValidation
  -> PersistedSilver
  -> Gold
```

## B2 work model

Incremental processing narrows work to affected business keys rather than rebuilding all Silver state. The implementation also carries durable progress and completion evidence so a crash/restart can distinguish completed work from work that still needs execution.

Gold provenance records the Silver snapshot identity when persisted Silver is the Gold source. This permits later cycles to avoid rebuilding Gold when the already-materialized Gold state names the current source Silver snapshot.

## Safety invariants

- Persisted Silver must not become the Gold source while shadow validation is disabled.
- Unsupported rollout tuples must fail startup validation.
- A passing shadow comparison may be certified durably.
- An absent, unreadable, malformed or wrong-version shadow receipt means "not certified" and comparison must run.
- Rollback mode preserves the ability to use incremental Silver while retaining legacy Gold behavior.

## Traceability anchors

- `iceberg/common/cutover.py::RUNTIME_ROLLOUT_MATRIX`
- `iceberg/common/cutover.py::validate_runtime_config`
- `iceberg/medallion/iceberg_medallion.py`
- `docs/adr/0001-incremental-silver-and-gold.md`
- `artifacts/b2-rollout/07-rollout-result.md`
