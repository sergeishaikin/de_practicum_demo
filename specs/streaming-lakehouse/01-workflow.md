# Layer 1 — Workflow

## Primary streaming flow

```text
OrdersProducer
  -> Kafka
  -> SparkStructuredStreaming

SparkStructuredStreaming
  -> PostgreSQL:marts.streaming_orders
  -> MinIO:streaming/orders_raw

MinIO:streaming/orders_raw
  -> IcebergWriter
  -> Iceberg:bronze.orders

Iceberg:bronze.orders
  -> MedallionProcessor
  -> Iceberg:silver.orders_clean
  -> Iceberg:gold.orders_daily_metrics

Iceberg tables
  -> Trino
  -> analytical consumers
```

## Boundaries

- Spark does not write Iceberg directly.
- Spark lands raw Parquet in MinIO.
- `iceberg-writer` is the ownership boundary for `landing -> bronze`.
- `iceberg-medallion` owns `bronze -> silver -> gold`.
- The Iceberg REST catalog is metadata/control-plane state, not a data-processing stage.
- MinIO stores the underlying data files.
- Trino queries Iceberg via the REST catalog and MinIO.
- Airflow does not orchestrate the Spark streaming path.

## Optional planes

Governance, observability, BI and developer tooling are orthogonal to the core streaming data path. They observe or consume the platform but do not define the correctness of the core ingestion flow.

## Traceability anchors

- `README.md`
- `iceberg/writer/iceberg_writer.py`
- `iceberg/medallion/iceberg_medallion.py`
- `docker-compose.yml`
- `docker-compose.extended.yml`
