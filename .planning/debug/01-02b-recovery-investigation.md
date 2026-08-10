# 01-02B-R read-only investigation result

Date: 2026-08-10  
Mode: three parallel Luna workers, read-only  
Base: `cedbb5b`  
Runtime mutation: none

## Verdict

`RECOVERY_NOT_PROVEN` → `STOP`.

The current Kafka log and the persisted outputs are real and inspectable, but
there is no durable canonical source that proves the complete required event
range and no source-generation identity that makes the new numeric offsets
distinct from the historical epoch. Recovery is therefore not authorized.

## Parallel findings

### Kafka/Docker identity

- Docker control plane is available; Kafka is healthy and producer/streaming are
  exited.
- Cluster ID: `5L6g3nShT-eMCtK--X86sw`.
- Topic `orders`, topic ID `Or9LdYWRRfCPHWtaGY6Pvw`, one partition, bounds
  `0..40208` (exclusive high watermark `40209`).
- Broker writes to `/tmp/kafka-logs` on the container overlay. Compose declares
  no Kafka service volume; the mounted anonymous data volume is not the active
  log directory. A recreate can therefore replace the Kafka epoch while
  MinIO/checkpoints/outputs persist.

### Checkpoints and outputs

- All four checkpoint prefixes terminate at source offset `157`.
- Landing, Bronze, Silver, and reconciliation output terminate at offset
  `218960`, with `218961` rows and equal Bronze/Silver digest
  `235686e5906e72d284f30513b8165f31ec4385f167c5d713c635e9ba225277d3`.
- Current Kafka observations `0..40208` are absent from Bronze. PostgreSQL is
  not authoritative for this gate because it contains `218963` rows including
  legacy NULL-version/debug rows.

### Canonical replay feasibility

- The producer uses nondeterministic UUID/random/wall-clock generation and has
  no event archive, seed, epoch ID, or payload hash.
- Valid Landing/Bronze data retains structured fields, not original JSON bytes,
  canonical hashes, topic/cluster identity, or source generation.
- Dead-letter retains raw payload only for invalid records; reconciliation and
  checkpoints retain counts/offset state, not canonical events.
- New landing paths/load IDs would append to Bronze; existing Silver guards do
  not prove canonical completeness or replay identity.

## Decision

Do not create a named checkpoint epoch. Do not start recovery. Do not unblock
`01-02C`. Preserve historical `01-02B = STOP` and all existing checkpoints.
