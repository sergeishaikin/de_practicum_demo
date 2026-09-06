# NG-4.6 — BuildKit cache efficiency experiment

> **Lifecycle:** PLANNED
> **Gate:** EXPERIMENT
> **Change:** `evaluate-buildkit-cache-efficiency`
> **Authorization:** NONE

## Objective

Measure whether additional BuildKit/Buildx caching materially improves local and CI image-build time without weakening reproducibility, bloating runtime images or making cache state part of correctness.

## Baseline gap

The repository already uses modern Docker builds and contains deliberate cache-aware Dockerfile ordering. In particular, the Spark Dockerfile places the large pinned runtime-JAR download before the frequently edited submit wrapper so ordinary wrapper edits do not invalidate that expensive layer. CI also uses Buildx for at least the Airflow E2E image build. The gap is therefore not "BuildKit is missing"; it is the absence of measured evidence for whether cache mounts and/or CI cache export/import would produce a worthwhile improvement on the remaining expensive steps.

## Scope

- identify the slowest reproducible first-party image builds and the layers responsible for cold versus warm cost;
- measure a clean baseline for cold build, warm no-change rebuild and a representative source-only edit;
- evaluate bounded BuildKit cache mounts for package/JAR downloads where they do not enter the runtime image;
- evaluate CI cache import/export only if it can be tied safely to lockfiles/Dockerfile inputs and cannot substitute stale artifacts for required rebuilds;
- compare resulting image digests/content where equivalent output is expected;
- adopt only mechanisms that show a useful, repeatable improvement.

## Non-goals

- Optimising Dockerfiles solely for fewer lines/layers.
- Removing `--require-hashes`, image digests, lockfiles or pinned JAR coordinates for speed.
- Making a remote registry mandatory for local development.
- Multi-platform builds unless a separate requirement introduces ARM/other targets.
- Treating a one-off fast run as evidence of an improvement.

## Requirements

### Requirement: The experiment starts from measured build scenarios

At minimum the experiment SHALL measure cold build, warm no-change rebuild and one representative edit that should preserve expensive dependency layers.

### Requirement: Cache does not become correctness

Deleting all BuildKit caches SHALL still produce the same functional runtime from the committed lockfiles, digests and build inputs.

### Requirement: Reproducibility controls are preserved

No accepted optimisation may remove dependency hashes, immutable base-image references or pinned runtime dependencies.

### Requirement: Adoption requires repeatable benefit

A cache mechanism SHALL be adopted only if repeated measurements show a material improvement on at least one expensive repository build path without a material regression on another required path.

## Acceptance evidence

The archived change SHALL contain:

- hardware/runner identity and Docker/Buildx versions;
- before/after timings for cold, warm and representative-edit scenarios, repeated enough to show variance rather than one sample;
- layer/cache-hit evidence identifying where the time changed;
- image size and, where deterministic output is expected, content/digest comparison;
- a clean-cache rebuild proving correctness does not depend on persisted cache;
- an explicit outcome per tested mechanism: `ADOPT`, `REJECT` or `DEFER`, with reason.

## Rollback

This is an experiment. Rollback removes the cache configuration and returns to the current Dockerfile/build commands; no runtime data or image contract depends on cache persistence.

## Hard stops

Stop before adoption if gains are within run-to-run noise, if cache invalidation cannot be explained from declared inputs, if a mechanism can reuse artifacts across incompatible lockfile/Dockerfile states, or if it requires weakening reproducibility controls.

## Freshness of external assumptions

BuildKit/Buildx cache backends and GitHub Actions cache behavior evolve quickly. Reverify primary Docker/GitHub documentation and runner limits at promotion, then benchmark the current Dockerfiles rather than this 2026-09-06 snapshot.