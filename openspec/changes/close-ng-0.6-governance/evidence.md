# Evidence: close-ng-0.6-governance

## Preflight

- `main` and `origin/main` at `249e0bc`; branch `governance/close-ng-0.6` cut
  from it, `git merge-base --is-ancestor` confirmed.
- `git ls-remote --heads origin` returns exactly three refs: `main`,
  `feature/ng-0.7-grafana-correlation`, `governance/branch-closure-rule`.
  Neither recorded exception branch is present, which is the fact the spec
  rewrite depends on.

## The exceptions' end conditions, tested against what happened

| Branch | Recorded end condition | What satisfied it |
| --- | --- | --- |
| `feature/ng-0.6-loki` | NG-0.6 resolves through a change branched from current `main`, its receipt is produced against `main`, and the work integrates | `feat/ng-0.6-adoption` branched from base `main@acbce84a`, verified against it, integrated by PR #14 as merge `978863de` |
| `test/dbt-extensive-testing` | NG-0.6 evidence is re-anchored to immutable identity, after which the branch anchors nothing | All seven citations re-anchored in this change and enforced by `test_evidence_citing_a_pull_request_run_records_its_base` |

Both conditions are met, so the exceptions are closed rather than waived.

## Evidence-shape detector, before and after

Run against `origin/main`'s `openspec/changes` tree — **5 findings**:

```text
2026-08-19-diagnose-cold-start-r1-e2e/evidence.md    :: The observed run
2026-08-19-fix-m3-recovery-progress-read/evidence.md :: Live proof — three H1 successes on one SHA
2026-09-04-add-loki-log-backend/evidence.md          :: Failed closure attempts and the lifecycle-safe test repair
2026-09-04-add-loki-log-backend/evidence.md          :: Why this closure was re-derived rather than merged
2026-09-04-standardize-trunk-based-development/evidence.md :: Milestone 1 — measured repository state
```

Against this branch: `clean`. **No exemption list exists**, which was the
condition the deferral set.

The detector reports **7** sections as `pull_request` citations, above the
non-vacuity floor of 5, so the clean result is not an empty scan.

## Non-vacuity

- `test_evidence_shape_rule_has_citations_to_check` fails if the detector finds
  fewer than five citations, so the rule cannot pass by matching nothing.
- `test_evidence_shape_detector_reports_a_synthetic_violation` asserts a
  citation without a base is caught, and that both the inline and the tabulated
  base forms satisfy it.
- `test_evidence_shape_detector_ignores_prose_about_the_trigger` pins the
  paragraph the first draft wrongly flagged, so the trigger cannot be widened
  back into prose that names no run.

## Completion gate

| Check | Result |
| --- | --- |
| `uv run --locked ruff check .` | All checks passed |
| `uv run --locked black --check .` | 111 files unchanged |
| `uv run --locked mypy` | Success: no issues found in 10 source files |
| `uv run --locked pytest` | 623 passed, 1 skipped, 81 deselected |
| `pytest tests --cov=iceberg --cov-fail-under=90` | Required coverage reached — 92.62% |
| `openspec validate --specs` | 8 passed |
| `openspec validate --changes` | 1 passed |

## Pending

- Pull request against `main`: head SHA, base branch, base SHA and required
  check run ids, recorded here once opened.
- Adoption and archival after integration.
