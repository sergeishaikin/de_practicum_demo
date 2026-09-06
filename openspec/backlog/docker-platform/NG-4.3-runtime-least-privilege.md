# NG-4.3 — Container runtime least privilege

> **Lifecycle:** PLANNED
> **Gate:** ADOPT
> **Change:** `harden-container-runtime-privileges`
> **Authorization:** NONE

## Objective

Reduce avoidable container privilege and host exposure while preserving the local platform's real stateful and development requirements.

## Baseline gap

Airflow, Spark and Jupyter custom images already run as non-root after privileged build steps. `iceberg/Dockerfile` declares no runtime `USER`, and `iceberg-rest` is explicitly configured as `user: "0:0"`. Airflow binds its host UI to `127.0.0.1`, while multiple extended-stack ports are published without an explicit loopback address. The reviewed Compose configuration does not establish a repository-wide contract for `read_only`, `tmpfs`, `cap_drop` or `no-new-privileges`.

## Scope

- inventory effective UID/GID, published host ports, writable filesystem paths and Linux capabilities for every first-party/custom container and selected third-party services;
- remove root runtime where it is not required, with explicit documented exceptions where it is;
- bind host ports to loopback by default unless LAN exposure is an intentional documented requirement;
- evaluate `read_only`, tmpfs-backed writable paths, `cap_drop` and `no-new-privileges` per compatible service;
- prove developer workflows, stateful storage and health checks still function under the hardened configuration.

## Non-goals

- A blanket rule that every third-party container must be non-root or read-only.
- Rebuilding upstream images solely to change UID when the risk/benefit is poor.
- Kubernetes PodSecurity, SELinux/AppArmor policy engineering or host firewall redesign.
- Removing write access from stateful paths that legitimately require it.

## Requirements

### Requirement: Runtime root is an exception

First-party/custom application containers SHALL run non-root unless a measured compatibility requirement prevents it. Every retained root runtime SHALL record the exact reason and the smallest privilege boundary available.

### Requirement: Local services are not unintentionally LAN-exposed

A host-published port used only from the developer machine SHALL bind to loopback. Any service intentionally exposed beyond loopback SHALL have that requirement documented.

### Requirement: Filesystem and kernel privileges are minimized safely

`read_only`, tmpfs, dropped capabilities and `no-new-privileges` SHALL be applied only where live acceptance proves the service's required startup, runtime and maintenance operations still work.

### Requirement: Hardening does not weaken diagnosability

A hardened container SHALL remain debuggable through documented logs/status/exec procedures appropriate to the service; security controls SHALL NOT silently disable required health or recovery evidence.

## Acceptance evidence

The archived change SHALL include:

- a before/after matrix of effective user, host bind address, writable paths and applied security options;
- exact counts of root-running first-party/custom containers before and after, with every retained root case justified;
- a host-listener proof showing local-only ports are loopback-bound;
- live startup and representative workload tests for each hardened service;
- at least one negative test demonstrating a removed privilege or forbidden write is actually blocked;
- clean-stack and existing integration evidence showing canonical data behavior is unchanged.

## Rollback

Hardening SHALL be revertible service by service. Rollback SHALL restore prior runtime identity/exposure without deleting persistent volumes or altering table/stream semantics.

## Hard stops

Stop if a proposed control breaks required state persistence, makes a service falsely healthy/unhealthy, forces privileged workarounds elsewhere, or cannot be distinguished from cosmetic configuration.

## Freshness of external assumptions

Reverify pinned image runtime-user requirements and Docker security-option semantics at promotion. Remeasure effective users and listeners from current `main`.