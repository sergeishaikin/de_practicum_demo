# NG-4.5 — Container image supply-chain assurance

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `add-container-supply-chain-assurance`
> **Authorization:** NONE

## Objective

Add an auditable CI contract for the software carried by pinned container images: vulnerability status, SBOM inventory and controlled refresh of immutable digests.

## Baseline gap

The repository already does the reproducibility part well: third-party images are pinned by digest, custom base images are digest-pinned, Python dependencies are installed with `--require-hashes`, uv is pinned, and Spark runtime JAR coordinates are locked. The missing layer is continuous evidence about what those immutable artifacts contain and when a pinned digest should be refreshed. Repository search on 2026-09-06 found no Trivy-based image vulnerability gate and no standing SBOM/provenance requirement.

## Scope

- generate a machine-readable inventory of every runtime image used by the Compose stack, resolving both external images and locally built images;
- produce SBOMs for the locally built runtime images and, where supported/reasonable, the consumed external images;
- run a vulnerability scanner against the resolved immutable images;
- define severity/fix-availability policy and an explicit exception format so the gate is not "zero CVEs forever";
- ensure scanner database/tool versions and scan timestamps are recorded in evidence;
- define a controlled digest-refresh path that opens reviewable changes rather than switching back to mutable tags;
- retain digest pinning and dependency hashing as standing reproducibility invariants.

## Non-goals

- Replacing all upstream images with custom hardened rebuilds.
- Blocking on unfixed low-value CVEs without a policy decision.
- A private image registry solely for this capability.
- Image signing/provenance enforcement unless it materially fits the selected implementation; signing may be a separately authorised follow-on.
- Scanning host packages outside the container/runtime dependency surface.

## Requirements

### Requirement: Every runtime image has immutable identity

The assurance inventory SHALL resolve each runtime image to an immutable digest. The change SHALL NOT regress pinned external images back to mutable tag-only references.

### Requirement: Locally built images have SBOM evidence

Each first-party built runtime image SHALL produce a machine-readable SBOM tied to the exact image digest tested in CI.

### Requirement: Vulnerability policy is explicit and reviewable

The CI gate SHALL define which findings fail, warn or require a time-bounded exception. Policy SHALL consider at least severity and fix availability, and SHALL record rather than silently suppress accepted findings.

### Requirement: Scan evidence names the artifact actually tested

A scan receipt SHALL name image digest, scanner/tool version, vulnerability database freshness and conclusion. A scan of a mutable tag without the resolved digest is insufficient adoption evidence.

### Requirement: Digest refresh stays controlled

Automated or assisted image updates MAY propose new digests, but adoption SHALL still occur through the repository's normal branch/PR/verification workflow.

## Acceptance evidence

The archived change SHALL contain:

- exact image inventory count, with external versus first-party-built classification;
- SBOM artifacts for every first-party built runtime image, linked to digests;
- vulnerability scan results against the same digests used by the acceptance candidate;
- a synthetic policy test proving a disallowed finding fails the gate and an allowed exception has explicit metadata;
- evidence that mutable tag-only substitution is rejected by a fitness rule;
- at least one controlled digest-update dry run or PR-shaped proof demonstrating the refresh workflow without bypassing review;
- existing live integration gates green on the scanned candidate.

## Rollback

The scanner/SBOM CI jobs MAY be disabled or reverted without changing the runtime images themselves. Runtime rollback SHALL continue to use previously accepted pinned digests rather than mutable tags.

## Hard stops

Stop if the selected tooling cannot tie results to immutable image identity, requires uploading proprietary repository contents to an unapproved third party, or the proposed policy would either fail permanently on unavoidable findings or silently ignore all findings.

## Freshness of external assumptions

Scanner capabilities, SBOM standards, vulnerability feeds and GitHub/Docker attestation features change quickly. Reverify primary documentation and tool versions at promotion; re-inventory current images from `main`.