## Context

See proposal.md — Why. Two constraints shape the approach.

The mechanism is documented Docker behaviour and the compose file shows the
mount pair, so this is not an open investigation in the way the R1 failure was.
What is missing is narrow: the observed ownership on the runner. Spending a
dedicated 180-minute rebuild to confirm textbook behaviour would be ceremony —
but claiming it without looking would be the "verified by assertion" failure the
verification contract exists to prevent.

The resolution is that H1 runs on every push to this PR anyway. A read-only
probe rides along on a run that was going to happen, so provenance costs nothing
and is still observed rather than assumed.

## Goals / Non-Goals

**Goals:**

- Observe the ownership and permissions of the checked-out `dbt/` on the runner
  immediately before the step that fails.
- Fix the mutation at its owner, so the next thing that reads `dbt/` on a clean
  runner does not hit the same wall.

**Non-Goals:**

- Making the `cp` succeed by force. `chmod`, `chown` and `sudo` are excluded by
  the fence precisely because they would work.
- Changing what dbt does or how the DAGs consume profiles.
- Fixing the other H1 layers or the warehouse CI blocker.

## Decisions

**Probe unconditionally, not on failure.** The R1 change learned this the
expensive way: a capture step scoped `if: failure()` collects nothing when the
run fails somewhere else, and nothing at all when it passes. Ownership of a
directory is cheap to print and interesting whether or not the step later fails,
so the probe runs always and is `|| true` throughout.

**Probe immediately before the failing step.** Ownership at that instant is the
question. Earlier is a different fact — the mutation happens when compose starts,
which is several steps back.

**The remedy targets the mount, not the copy.** If the observation confirms case
A, the wrong thing is a bind mount whose target path is inside another
read-write bind mount of the host checkout: Docker materialises a host file the
runner then cannot replace. The minimal correction keeps the container seeing a
profiles file while no longer creating one in the checkout — mounting the
example to a path outside `/opt/airflow/project/dbt`, or giving dbt an explicit
profiles directory, rather than layering a file mount inside a directory mount.
The concrete form is chosen once the observation is in, because case B or C
would point elsewhere. Alternative considered: have the workflow write
`profiles.yml` somewhere else — rejected, that moves the victim and leaves the
checkout still mutated for every later reader.

**Prove the fix by the same probe.** Whatever the remedy, the following H1 run
must show `dbt/` owned by the runner and the `cp` succeeding. That is a
demonstrated fix, not an argued one.

## Risks / Trade-offs

- **The probe may show case C** — no container mutation, ownership intact, and a
  different reason for `Permission denied`. Then this change's remedy section is
  wrong and the design has to be revisited before anything is applied. That is
  the point of observing first.
- **Fixing the mount changes how Airflow finds its profiles.** `Cosmos
  ProfileConfig` in both DAGs points at `/opt/airflow/project/dbt/profiles.yml`.
  Any relocation has to keep those paths working, and `tests/test_dags.py` and
  `ci-s1-dbt.yml` are the checks that would catch a mistake.
- **One layer at a time.** Fixing this one will let H1 reach `Prometheus and
  Grafana smoke`, which has also never executed. A fifth layer appearing is a
  likely outcome and not a failure of this change.
