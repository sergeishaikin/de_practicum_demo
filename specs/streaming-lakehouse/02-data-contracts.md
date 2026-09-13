# Layer 2 — Data Contracts

## Bronze: `bronze.orders`

```text
BronzeOrder {
  order_id: string?
  customer: string?
  amount: double?
  country: string?
  status: string?
  event_time: timestamp?
  kafka_timestamp: timestamp?
  kafka_partition: int?
  kafka_offset: long?
  event_date: date?
  business_version: long?
  source_epoch_id: string?
  event_id: string?
  canonical_payload: string?
  canonical_payload_hash: string?
}
```

Partitioning:

```text
PARTITION BY day(event_date)
```

The four canonical lineage fields are additive and optional so older landing files remain appendable.

## Silver: `silver.orders_clean`

```text
SilverOrder {
  order_id: string?
  customer: string?
  amount: double?
  country: string?
  status: string?
  event_time: timestamp?
  kafka_timestamp: timestamp?
  kafka_partition: int?
  kafka_offset: long?
  event_date: date?
  business_version: long?
}
```

Partitioning:

```text
PARTITION BY day(event_date)
```

Semantic role: cleaned and deduplicated business representation of Bronze orders.

## Gold: `gold.orders_daily_metrics`

```text
DailyMetrics {
  event_date: date?
  country: string?
  status: string?
  orders_count: long?
  total_amount: double?
  avg_amount: double?
  distinct_customers: long?
}
```

Semantic grain:

```text
(event_date, country, status)
```

## Contract notes

- `business_version` is the domain ordering field for deduplication semantics.
- Kafka partition/offset remain transport metadata and are not the business ordering authority.
- Schema evolution into Bronze is additive in the current writer path.

## Traceability anchors

- `iceberg/writer/iceberg_writer.py::TABLE_SCHEMA`
- `iceberg/writer/iceberg_writer.py::PARTITION_SPEC`
- `iceberg/medallion/iceberg_medallion.py::SILVER_SCHEMA`
- `iceberg/medallion/iceberg_medallion.py::GOLD_SCHEMA`
