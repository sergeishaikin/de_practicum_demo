# Layer 3 — Behavior

## Landing discovery

```text
Landing Parquet object
  -> inspect Spark FileStreamSink metadata
  -> if object is not represented in committed metadata: ignore
  -> if object is already recorded as done: ignore
  -> otherwise: include in next writer batch
```

Presence of a Parquet object in MinIO is not sufficient evidence that Spark committed it. The `_spark_metadata` log is the commit authority for landing ingestion.

## Landing -> Bronze

```text
Committed landing files
  -> read as Arrow dataset
  -> normalize timestamp representation
  -> ensure/evolve Bronze table
  -> append to bronze.orders
  -> stamp Iceberg snapshot with load-id
  -> publish Bronze outbox record
  -> persist local writer progress
```

A successful Bronze append and publication of downstream work are separate steps. Recovery logic therefore treats catalog state and local state independently.

## Bronze -> Silver

Conceptual business flow:

```text
bronze.orders
  -> identify applicable work
  -> apply quality/validity rules
  -> resolve multiple business versions per order_id
  -> retain winning business state
  -> write/replace affected Silver state
```

The implementation supports both legacy full rebuild and B2 incremental processing; the selected behavior is controlled by validated runtime configuration.

## Silver -> Gold

```text
Silver business state
  -> group by event_date, country, status
  -> orders_count
  -> total_amount
  -> avg_amount
  -> distinct_customers
  -> gold.orders_daily_metrics
```

Gold may be rebuilt from a legacy path or sourced from persisted Silver depending on rollout mode.

## Lineage behavior

Current emitted lineage includes:

```text
landing -> bronze
bronze -> silver
silver -> gold
```

`Kafka -> landing` is a documented gap rather than a falsely claimed edge.

## Traceability anchors

- `iceberg/writer/iceberg_writer.py::committed_landing_paths`
- `iceberg/writer/iceberg_writer.py::list_new_files`
- `iceberg/writer/iceberg_writer.py::read_batch`
- `iceberg/writer/iceberg_writer.py::publish_outbox`
- `iceberg/medallion/iceberg_medallion.py`
- `docs/LINEAGE.md`
