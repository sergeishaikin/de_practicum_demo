---
gsd_findings_version: 1.3
task: docker-storage-investigation
mode: quick
created: 2026-08-16
status: kafka-recovered-prevention-staged-awaiting-deployment
---

# Docker storage incident — investigation, recovery, prevention

Revision 1.1 corrects three errors in the first draft; each is marked
**[corrected]** below. Corrections came from peer review and were then verified
against the running stack rather than accepted on assertion.

## Outcome

| Measure | Before | After |
|---|---|---|
| Docker VM disk used | ~938 GB / 1006.9 GB (98%) | **56.7 GB (6%)**, 899 GB free |
| `de-demo-spark-worker` writable layer | 965 GB | ~1 GB |
| `/opt/spark/work` | 900 GB, 681 app dirs | 56 KB, 1 app dir |
| `docker system df` Images | 996.2 GB (anomalous) | **30.86 GB** |
| `de-demo-postgres` | ENOSPC crash loop | healthy |
| Warehouse data | — | unchanged: 8 pipeline runs, 1000 stg orders, 1000 core orders, 1149 core items |

## 1. The 996 GB "images" figure **[corrected]**

The first draft derived real image storage as
`996.2 GB Images − 966.2 GB Containers ≈ 30 GB`. **That is not a valid Docker
accounting identity.** Image layers and container writable layers are distinct
concepts, and `docker system df` totals have had their own accounting bugs.

The load-bearing evidence is the direct measurement instead: the Spark worker
held ~965 GB of writable data, of which `/opt/spark/work` was ~900 GB.

The ~30 GB estimate did turn out to be right — after the cleanup
`docker system df` reports Images at **30.86 GB** — but that is corroboration
after the fact, not a derivation. Do not compute image storage by subtraction.

## 2. Root cause: unbounded per-submission JAR staging

1. `spark/submit-with-runtime.sh` passed every JAR under `/opt/spark/h1-jars`
   to `--jars` as an ordinary filesystem path — 678 MB, of which
   `bundle-2.29.52.jar` (AWS SDK v2) is 612 MB. Spark therefore treated them as
   files needing distribution and copied the whole set into a fresh
   `/opt/spark/work/app-*/<executor>/` directory on **every** submission.
2. `orders-streaming` carried `restart: unless-stopped` against a job that is
   *deliberately* fail-closed on unavailable Kafka history, so it resubmitted
   every ~22 seconds — app IDs `app-…-0000` → `app-…-1339` within ~24 hours.
3. **[corrected]** The first draft claimed worker cleanup was disabled because
   no `SPARK_WORKER_OPTS` was set. It was not. The worker log is explicit:

   ```
   26/08/16 10:09:43 INFO Worker: Worker cleanup enabled;
     old application directories will be deleted in: /opt/spark/work
   ```

   Cleanup is **enabled by default** in Spark 4.2.0. The defect is its default
   `appDataTtl` of 7 days: every one of the 681 directories was under 24 hours
   old, so Spark correctly considered all of them too young to remove.
4. The disk filled, and the job then failed *because of it* —
   `java.io.IOException: Failed to create a temp directory (under /tmp) after 10 attempts!`
   — shortening each cycle and accelerating the loop.

Measured burn rate: **~1.4 GB / 22 s ≈ 230 GB per hour.**

Only 681 work directories existed for 1339 submissions because the later
submissions failed at `spark-submit` before an executor was ever launched.

## 3. A time-based retention policy was never the fix

`find /opt/spark/work -maxdepth 1 -type d -mtime +3` returned **0**. A 3-day
policy would have freed nothing, and the disk refilled in ~4 hours.

A TTL is a guardrail, not the fix. Even 2 hours permits ~460 GB at the measured
burn rate. The fix is to stop staging the JARs at all.

## 4. Recovery, as executed

Every step was verified before the next.

1. **Stopped the growth source** — `docker stop de-demo-orders-streaming`.
   Stopping preserves the Spark checkpoints; it is not a reset, and it matches
   the fail-closed decision already recorded in `STATE.md`.
2. **Checked for live applications before deleting anything.** This mattered:
   the Spark master reported one `RUNNING` app,
   `app-20260815191948-0000` — the **Spark Connect server** — and it owned the
   *oldest* directory in the work dir. A blind `rm -rf /opt/spark/work/app-*`
   would have deleted a running application's directory.
3. **Deleted only the 680 terminated directories**, preserving that one.
4. **Verified**: VM disk 6% used, `docker system df` sane, Postgres exited the
   crash loop and returned to healthy on its own, warehouse row counts identical
   to pre-incident.

The 22.5 GB orphan volume `b420157…` (a stale Docker engine data root,
`engine-id 591dda73-…`, 21 container dirs matching no live container) was
**not** removed. With 899 GB free it is no longer urgent, and it is an
irreversible deletion.

## 5. Host disk versus VM disk **[corrected]**

`C:\Users\serge\AppData\Local\Docker\wsl\disk\docker_data.vhdx` is **991.3 GB**
and does not shrink when data inside the VM is deleted.

The first draft listed Docker Desktop → *Troubleshoot → Clean / Purge data* as
a compaction option. **That is wrong and dangerous — it resets Docker data**,
which would have destroyed every volume classified as REQUIRED in this same
document, including `de_demo_pg_data` and the MinIO/Iceberg state. It has been
removed.

Compaction is a separate, Docker-Desktop-version-specific operation to perform
only on a healthy stack (`wsl --manage docker-desktop-data --set-sparse true`,
`Optimize-VHD`, or the built-in reclamation in Docker Desktop ≥ 4.34). With
2.3 TB free on `C:` it is not urgent.

## 6. Prevention landed

| Change | File |
|---|---|
| JARs referenced as `local:/opt/spark/h1-jars/…` so Spark does not distribute what is already baked into every image | `spark/submit-with-runtime.sh` |
| `SPARK_WORKER_OPTS` with `cleanup.interval=300`, `appDataTtl=900` (15 min) as a guardrail | `docker-compose.extended.yml` |
| `restart: on-failure:3` instead of `unless-stopped` for a deliberately fail-closed job | `docker-compose.extended.yml` |
| `x-bounded-logging` anchor (`max-size: 50m`, `max-file: 3`) applied to the seven Spark/streaming/iceberg services | `docker-compose.extended.yml` |

`local:` was chosen over `spark.executor.extraClassPath` because it preserves
normal driver/executor dependency semantics instead of requiring the two
classpaths to be managed separately.

Verified: `docker compose config --quiet` passes; the rendered config shows
`restart: on-failure:3`, the logging options, and the three worker cleanup
properties; `bash -n` passes on the wrapper; the wrapper's find/sed pipeline
emits `local:/opt/spark/h1-jars/…` correctly.

Not yet applied to the live stack — that needs a `compose up` and an image
rebuild for the wrapper change, which is a separate authorized action.

## 7. The original retention question, now measurable

| Table | Rows | Range | Older than 3 days | Size |
|---|---|---|---|---|
| `marts.lakehouse_metrics` | 8,804 | Aug 7 → Aug 16 | 8,306 (94%) | 1,664 kB |
| `marts.maintenance_runs` | 103 | Aug 7 → Aug 16 | 69 | 64 kB |
| `marts.pipeline_runs` | 8 | Aug 5 → Aug 16 | 3 | 48 kB |

`lakehouse_metrics` grows ~970 rows/day and is the only real retention
candidate — but it would take a year to reach ~65 MB. This is not a storage
problem. If a policy is wanted it should be defined **semantically** — on the
order of 90/180 days, with aggregation of older rows — rather than the original
3-day idea, which was aimed at a disk problem that turned out to live elsewhere.

`maintenance_runs` and `pipeline_runs` are **audit/evidence** tables referenced
by `STATE.md` phase records. They should not get a blanket time-based delete.

Separately: `marts.streaming_orders` occupies **46 MB while holding 0 rows** —
dead-tuple bloat from the upsert path. An earlier draft of this document
suggested `VACUUM FULL`; that is the wrong tool here. `VACUUM FULL` rewrites the
table under an `ACCESS EXCLUSIVE` lock, and 46 MB against 899 GB of free space
does not justify it. Plain `VACUUM (ANALYZE)` is the right call unless the bloat
is measurably hurting query plans.

## 8. Kafka — resolved: same incident, wider blast radius

`de-demo-kafka` did not fail independently. It was killed by the same disk
exhaustion, 3.5 hours before Postgres finally gave out:

```
[2026-08-16 15:16:01,256] ERROR Error while appending records to orders-0
  in dir /var/lib/kafka/data
java.io.IOException: No space left on device
[2026-08-16 15:16:01,507] ERROR Shutdown broker because all log dirs in
  /var/lib/kafka/data have failed
```

Kafka's log-dir failure handling is fail-fast by design: one failed dir, and
with no other dir available the broker shuts itself down. Exit code 1, restart
policy `no`, so it stayed down while the producer kept running against a broker
that was gone.

**The blast radius of the Spark disk exhaustion was therefore Postgres *and*
Kafka** — the two stateful stores in the stack.

Read-only inspection of `de_demo_kafka_data` (1.153 GB) shows it structurally
intact:

- `orders-0/00000000000000000000.log` is 50 MB and non-zero, with its `.index`
  and `.timeindex` present.
- The 50 zero-length `.log` files are all `__consumer_offsets-*` partitions.
  That is expected, not damage: Spark Structured Streaming keeps offsets in its
  own checkpoint and does not commit to `__consumer_offsets`.
- `cluster.id=5L6g3nShT-eMCtK--X86sw` and
  `directory.id=KVkjlSIJNaSMstmZOrNNFw` match the uuid named in the failure log;
  `partition.metadata` still carries its Aug 10 epoch.
- No clean-shutdown marker, so the next start runs a normal unclean-shutdown
  recovery scan. If the final append was torn mid-write, that scan truncates to
  the last valid record — designed behaviour, no loss of committed data.

The broker was **not** restarted; that is a stateful action for the controlled
stack change, where the recovery scan output should be read before anything
else is trusted.

## 9. The incident as an executable test scenario

The most valuable output here is not the reclaimed space — it is that the
incident traced a complete failure chain the orchestration/idempotency phase
should assert rather than merely document:

> dependency unavailable → job fails → restart policy activates → submission
> occurs → **scratch/resource growth stays bounded** → **stateful services stay
> intact** → dependency recovers → rerun resumes without duplication or
> checkpoint corruption

Every link in that chain failed here: the restart policy was unbounded, growth
was unbounded, and two stateful services were taken down by a third service's
scratch. Those are testable properties.

## 10. Stack recovery — executed and validated

### The "four stale duplicate containers" premise was wrong

Inspection before any deletion showed each of the four services has **exactly
one** container, it is the hash-prefixed one, and it is **running**:

| Service | Containers | State | Mounts |
|---|---|---|---|
| `spark-connect` | `7a18cc079146_…` only | running | none |
| `orders-producer` | `ff8f77f41bc2_…` only | running | none |
| `kafka-ui` | `661e2fdcf3d3_…` only | running | none |
| `observability-exporter` | `e31fb53765ba_…` only | running | none |

All four carry correct Compose labels (`project=de-practicum-demo` plus the
right `service`). They are the live singletons under renamed identities — the
residue of an interrupted Compose rename-before-recreate — not stale leftovers
sitting beside healthy counterparts. `7a18cc079146_…spark-connect` is the very
Spark Connect server that owns the preserved running application.

Deleting those four IDs would therefore have taken down four live services with
no replacement. **They were not removed.** The zero-mount check does pass, which
means they are safe to *recreate*, not safe to *delete now*.

Correct resolution: let Compose rename them through recreation. Compose matches
by label rather than name, so it only recreates services whose config changed —
`spark-connect` and `orders-producer` did (they gained the logging anchor) and
will get canonical names automatically; `kafka-ui` and `observability-exporter`
did not, so they need `--force-recreate` scoped to those two services. No
`--remove-orphans` anywhere.

### Kafka recovered independently, before any Compose change

Producer stopped first so recovery was not mixed with fresh writes, then
`docker start de-demo-kafka` on the existing container:

```
Recovering 51 logs from /var/lib/kafka/data since no clean shutdown file was found
WARN [LogLoader partition=orders-0] Corruption found in segment 0, truncating to offset 70143
Completed load of Log(topic=orders, partition=0, … logEndOffset=70143) with 1 segments
STARTING → RECOVERY → RUNNING … Kafka Server started
```

The predicted torn write was real and was handled exactly as designed:
truncation to the last valid record.

Validation:

| Check | Result |
|---|---|
| Broker healthy | `Up (healthy)` |
| Errors since restart | **0** |
| `orders` offset range | 0 → 70143, single partition, Leader 1, ISR [1] |
| TopicId | `GJvw-MROTyiERZC7fe1Ebg`, unchanged |
| Log dir | `de_demo_kafka_data` → `/var/lib/kafka/data`, the named volume |
| Producer restored | offsets advance ~2.3/s, matching `EVENTS_PER_SECOND: 2`, 0 broker errors |

The producer's stdout is block-buffered, so its `docker logs` tail is not a
live signal; the offset delta is. Its `_MSG_TIMED_OUT` lines are buffered
messages from the outage window, not current failures.

**New detail: Kafka was killed by disk exhaustion twice today**, at 09:10:29 and
again at 15:16:01 — so the loop had already taken the broker down once before
the second, final failure.

### Rebuild cost fixed before rebuilding

`spark/Dockerfile` copied `submit-with-runtime.sh` *before* the `RUN` that
downloads the pinned JAR set, so editing the wrapper invalidated a 678 MB
download layer. The `COPY` now comes after that `RUN` (with `chmod +x` preserved
— the file is tracked mode `100644`), so future wrapper edits are free.

## 11. Still open

- Orphan volume `b420157…` (22.5 GB) and the dead `03-orchestration` / `op-*`
  volumes (~71 MB) — classified safe, deliberately left alone: with 899 GB free
  there is no operational reward for an irreversible action.
- Applying the prevention branch as a controlled stack change, verifying:
  `local:` JAR handling actually in use; worker reporting TTL 900 / interval
  300; deterministic streaming failure stopping after three retries; log
  rotation active; Spark Connect surviving recreation; Postgres/MinIO/Kafka
  volumes retaining state.
- VHDX compaction — optional housekeeping, not recovery, with 2.3 TB free on `C:`.
- A disk-space guard/alert.
