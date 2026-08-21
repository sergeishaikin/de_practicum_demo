## Verification receipt

Commit under test: `9c31999`.

| Run | Workflow | Conclusion |
|---|---|---|
| [32353968072](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32353968072) | CI | success |
| [32353968085](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32353968085) | M5 architecture gates | success |
| [32353968001](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32353968001) | S1 dbt semantic lineage | success |
| [32353967937](https://github.com/sergeishaikin/de_practicum_demo/actions/runs/32353967937) | H1 clean reproducible stack | success |

Host gate: ruff and black clean, `mypy` clean over 9 files, **481 passed**,
coverage **94.65%** — unchanged from before this change, which is correct: it
adds no `iceberg/` code.

### The claim this change exists to disprove, disproved

The premise was that Docker Desktop being stopped meant live dependencies were
unavailable. The engine was checked directly:

```text
docker info --format '{{.ServerVersion}}'   -> 29.5.3
Docker Desktop process                      -> running
```

It had been available throughout. NG-0.1's archived evidence claimed its
provenance receipt "could not run locally — no live catalog or object store
here". Run against a local MinIO + REST-catalog profile:

```text
tests/integration/test_provenance_receipt.py    1 passed in 2.07s
```

That evidence file now carries a dated correction rather than a quiet edit.

### The local procedure, executed end to end

Started the minimum profile, waited for readiness, ran the live gates, measured,
and stopped it again:

```text
readiness                       iceberg-rest healthy on the first poll (<5s)
M5 live gates (9 tests)         9 passed in 31.09s
minio / iceberg-rest / postgres 397 / 250 / 46 MiB  = ~0.7 GB of 15.49 GB
```

The same suite in CI occupies a whole job. That ratio is the argument for the
policy, not the policy itself.

### It paid for itself inside this change

H1 failed on `9c31999`'s predecessor with the NG-0.2 Airflow probe asserting
against `ListenerManager.listeners`, which does not exist in Airflow 3.3. Rather
than guess and spend another twenty-minute cycle, the image was interrogated
directly:

```text
public attrs: ['add_hookspecs', 'add_listener', 'clear', 'has_listeners', 'hook', 'pm']
```

and, with the OpenLineage configuration applied:

```text
PLUGINS: ['cosmos.listeners.task_instance_listener',
          'airflow.providers.openlineage.plugins.listener',
          'cosmos.listeners.dag_run_listener']
```

The listener **is** registered; the probe was wrong. Fixed and verified locally
in `5.52s`, then confirmed in H1 on this commit:

```text
tests/integration/test_airflow_lineage_provider.py .....   [ 13%]
============ 35 passed, 1 xfailed in 172.53s ============
```

The defensive probe design is what made this cheap: it recorded each signal
independently, so the failure arrived as `AttributeError: 'ListenerManager'
object has no attribute 'listeners'` rather than as a dead process.

### Found by measuring rather than reading

- **Six locally built images, not four.** `DEVELOPMENT.md` named Airflow, Spark,
  Jupyter and PyIceberg; `observability` and `orders-producer` are also built
  here. Nothing now lists them by hand.
- **Image-pin drift.** The committed `.env.example` pins every image by digest;
  this machine's `.env` pins `iceberg-rest` and `kafka-ui` at `:latest`. Local
  results are therefore not automatically comparable to CI.
  `test_committed_compose_pins_every_image` scans Compose, where these appear as
  `${VAR}`, so it structurally cannot see this — correct behaviour, but it left
  `.env.example` unguarded, and a new test now covers it.
- **A Compose network conflict.** Starting `docker-compose.yml` alone against an
  existing `de_demo_net` fails on a label mismatch, because the extended file
  declares that network `external`. Both `-f` flags are now documented as
  mandatory.

The local `.env` was **not** rewritten. An uncommitted file belongs to the
developer; the drift is reported instead.

### What this does not establish

- **One machine.** Every number here describes a single Windows host. The
  contract half is written to hold regardless; the snapshot is labelled as
  evidence and dated.
- **Contract sentences are checked by substring.** The guard catches deletion
  and heading moves. It cannot catch a rewrite that keeps a phrase and reverses
  the meaning around it.
- **Local is not CI.** CI runs on fresh volumes with digest-pinned images and no
  developer state. The policy orders them; it does not equate them.
