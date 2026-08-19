# Evidence

Run `32242181301`, SHA `709a139`, fresh volumes. The probe ran (`if: always()`),
so the observation exists even though the run failed earlier than the dbt step.

## Case A, confirmed

```text
## runner identity
uid=1001(runner) gid=1001(runner) groups=1001(runner),4(adm),100(users),118(docker),999(systemd-journal)

## workspace and dbt directory
drwxr-xr-x 31 runner runner 4096 Aug 19 10:24 .
drwxr-xr-x  7 runner runner 4096 Aug 19 10:23 dbt

-rw-r--r--  1 root   root       0 Aug 19 10:23 profiles.yml
-rw-r--r--  1 runner runner   391 Aug 19 10:20 profiles.yml.example

  File: dbt/profiles.yml
  Size: 0         	regular empty file
  Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid: (    0/    root)
  Birth: 2026-08-19 10:23:40.607570102 +0000

  File: dbt/warehouse/profiles.yml
  Size: 0         	regular empty file
  Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid: (    0/    root)
  Birth: 2026-08-19 10:23:40.608446272 +0000
```

Three facts settle it:

- **`dbt/profiles.yml` exists, is owned by `root:root`, and is zero bytes.** The
  runner is uid 1001 and cannot replace it, which is precisely
  `cp: cannot create regular file 'profiles.yml': Permission denied`.
- **Birth times separate checkout from stack start.** Everything else under
  `dbt/` was born at `10:20:23` owned by `runner`; both `profiles.yml` files were
  born at `10:23:40`, the moment `Build and start clean stack` ran.
- **The directory itself is untouched** — `dbt/` is still
  `drwxr-xr-x runner runner`. Case B is excluded, and case C is excluded because
  something clearly did mutate the checkout.

## The mutation's owner is the Docker daemon, not a container process

`docker inspect de-demo-airflow` reports `User=airflow`, and inside the container
`id` is `uid=50000(airflow) gid=0(root)`. A file written by that process would be
owned by 50000, not 0. The files are `root:root` and **empty**, which is the
signature of Docker creating a missing bind-mount target before mounting over it:
the content of `profiles.yml.example` appears at the container path, while the
host keeps the empty placeholder the daemon made.

The mount pair that causes it, from `docker-compose.yml`:

```yaml
- ./dbt:/opt/airflow/project/dbt:rw
- ./dbt/profiles.yml.example:/opt/airflow/project/dbt/profiles.yml:ro
- ./dbt/warehouse/profiles.yml.example:/opt/airflow/project/dbt/warehouse/profiles.yml:ro
```

Both targets are gitignored (`.gitignore:50`, `:54`), so on a fresh checkout they
do not exist and the daemon creates them — inside the read-write host mount.

This also predicts the same trap for a fresh **Linux developer clone** that runs
the stack before creating a profiles file, not only for CI. On this Windows
machine both files exist and are developer-owned, so Docker never creates them,
which is why the repository has never seen it.

## Also observed in this run

- **The run failed earlier, at `Bootstrap and wait for dependencies`:**
  `RuntimeError: Query ... failed: Trino server is still initializing`. That step
  passed in the two previous cold runs. It is another cold-start timing effect of
  the same family as the R1 failure, recorded here and not investigated — it
  belongs to its own change.
- **The R1 capture step fired for the first time** (`if: failure()` was satisfied
  by the bootstrap failure). Its output describes a stack where E2E never ran, so
  it does not advance the archived R1 question.

## After the fix — the checkout is no longer mutated

Run `32244969884`, SHA `f963e77`, fresh volumes, stack fully started
(`Build and start clean stack` succeeded).

```text
## the file the next step tries to create
stat: cannot statx 'dbt/profiles.yml': No such file or directory
dbt/profiles.yml: absent

## workspace and dbt directory
drwxr-xr-x  7 runner runner 4096 Aug 19 10:54 dbt
-rw-r--r--  1 runner runner  293 Aug 19 10:54 dbt_project.yml
-rw-r--r--  1 runner runner  391 Aug 19 10:54 profiles.yml.example
-rw-r--r--  1 runner runner   35 Aug 19 10:54 requirements.in
drwxr-xr-x  5 runner runner 4096 Aug 19 10:54 warehouse
```

Side by side with the same probe before the fix:

| | before (`709a139`) | after (`f963e77`) |
|---|---|---|
| `dbt/profiles.yml` | `root:root`, 0 bytes, born at stack start | **absent** |
| `dbt/warehouse/profiles.yml` | `root:root`, 0 bytes, born at stack start | absent |
| every other entry under `dbt/` | `runner:runner` | `runner:runner` |

The daemon no longer creates anything in the checkout, because no bind mount
targets a path inside it. This is the stronger outcome: not a file the runner can
overwrite, but no file at all.

**Still unproven: that `dbt semantic contract` passes.** This run died earlier, at
`Bootstrap and wait for dependencies`, so the dbt step was skipped. That is a
different H1 layer — `RuntimeError: Query ... failed: Trino server is still
initializing` — and it has now blocked two consecutive runs. It is diagnosed as
its own change; the boundary this change fixed is proven green independently of
it.

## Closing proof — `dbt semantic contract` executed and passed

Run `32247139737`, SHA `61a57ef`, fresh volumes.

```text
✅ Probe dbt directory ownership     dbt/profiles.yml absent, dbt/ runner-owned
✅ dbt semantic contract             Done. PASS=28 WARN=0 ERROR=0 TOTAL=28
                                     Completed successfully
```

The step ran end to end: `cp profiles.yml.example profiles.yml` succeeded, the
venv synced, dbt parsed, compiled, built both semantic views and ran all 28
tests. Both halves of the closing criterion are now met — the checkout is not
mutated, and the step that could not write into it no longer fails.

The step's exit code was still 1 on that run, but for an unrelated reason: its
own assertion demanded `PASS=26 ... TOTAL=26` while the project now declares 28.
That is a separate layer, fixed in `61a57ef`, and it does not qualify the proof
above — dbt's own summary is what proves the mount fix worked.

H1 then failed at `Prometheus and Grafana smoke`, a step that had never
executed. That is layer 6 and belongs to its own change.
