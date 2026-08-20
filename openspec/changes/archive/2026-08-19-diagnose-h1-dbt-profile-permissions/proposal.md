## Why

H1's clean rebuild now reaches `dbt semantic contract` and fails there in about
one second:

```text
cp: cannot create regular file 'profiles.yml': Permission denied
```

This is the fourth distinct layer that workflow has surfaced since it started
running past its own configuration, and the first one that is host-state rather
than service-state. The step is host-side and runs after build, bootstrap,
integration and E2E, so something between checkout and that line changed the
`dbt/` directory the runner had just checked out.

The cheap remedies — `chmod`, `sudo cp`, writing the file somewhere else — all
target the `cp`, which is the victim. The fix has to land on whatever performed
the host-state mutation, or the next thing that reads `dbt/` on a clean runner
hits it again.

## What Changes

- Establish who changed the ownership or permissions of the checked-out `dbt/`
  directory, distinguishing three cases: a `profiles.yml` that already exists
  and is owned by a container UID; a `dbt/` directory that became unwritable to
  the runner; or no container mutation at all, which would make this a workflow
  or checkout contract problem.
- Apply a minimal fix at the owner of that mutation once provenance is
  established, not before.
- No dbt model, Docker `USER`, retry or permission workaround is introduced.

## Capabilities

### New Capabilities

None. `skip_specs: true`.

### Modified Capabilities

None. The remedy is expected to be a mount or workflow correction, not a change
to what the system must do.

## Impact

- Affected workflow: `.github/workflows/ci-h1-clean.yml`, step `dbt semantic contract`.
- Affected configuration: the `dbt` bind mounts on the Airflow service in
  `docker-compose.yml`.
- Blocks: a truthful repository-wide H1 baseline, and therefore the operator's
  `H1 green` gate.

## Scope fence

Permitted:

- read-only diagnostics added to `.github/workflows/ci-h1-clean.yml`
- planning artifacts in this change
- after provenance is established: a minimal fix at the owner of the mutation

Not permitted:

- `chmod` or `chown` workarounds
- `sudo cp`
- retries or sleeps
- dbt model changes
- Docker `USER` changes
- bind-mount changes **before** provenance is established
- the warehouse CI blocker
- `04-08`

## Pre-change evidence

Read-only, from the repository and from run `32193696670`.

`docker-compose.yml` mounts the host `dbt/` directory read-write and then mounts
two files **into paths inside it**:

```yaml
- ./dbt:/opt/airflow/project/dbt:rw
- ./dbt/profiles.yml.example:/opt/airflow/project/dbt/profiles.yml:ro
- ./dbt/warehouse/profiles.yml.example:/opt/airflow/project/dbt/warehouse/profiles.yml:ro
```

The second and third targets do not exist on a fresh checkout — `dbt/profiles.yml`
and `dbt/warehouse/profiles.yml` are both gitignored (`.gitignore:50`, `:54`).
Docker creates a missing bind-mount target before mounting, and because that
target path resolves inside the read-write host mount, the file it creates lands
in the runner's checkout rather than only in the container.

That mechanism predicts case A exactly: `dbt/profiles.yml` exists and is owned by
the container UID by the time the workflow's `cp profiles.yml.example
profiles.yml` runs, so the copy cannot overwrite it. It also explains why no
developer has hit it — locally the file already exists before compose starts
(`CLAUDE.md` instructs copying it), so Docker never creates it. On this machine
both files exist and are owned by the developer, which is consistent with that
and, being Windows, proves nothing about the Linux runner.

```text
Predicted case:  A - Docker created the mount target inside the host checkout
Established:     NOT YET - the mechanism is documented behaviour, but the
                 ownership on the runner has not been observed
Missing evidence: `id`, `ls -ld dbt`, `ls -la dbt` and `stat dbt/profiles.yml`
                 taken on the runner immediately before the failing step
```

The missing evidence does not require a dedicated run: H1 executes on every push
to this PR, because a `pull_request` paths filter is evaluated against the whole
PR diff. A read-only probe added before the failing step is therefore paid for by
a run that happens anyway.
