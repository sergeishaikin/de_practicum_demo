from __future__ import annotations

import os

import psycopg2
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka:9092",
)
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "orders")

MINIO_BUCKET = os.getenv("MINIO_BUCKET", "de-practicum")
RAW_OUTPUT_PATH = os.getenv(
    "RAW_OUTPUT_PATH",
    f"s3a://{MINIO_BUCKET}/streaming/orders_raw",
)
RAW_CHECKPOINT_PATH = os.getenv(
    "RAW_CHECKPOINT_PATH",
    f"s3a://{MINIO_BUCKET}/checkpoints/orders_raw",
)
DEAD_LETTER_OUTPUT_PATH = os.getenv(
    "DEAD_LETTER_OUTPUT_PATH",
    f"s3a://{MINIO_BUCKET}/streaming/orders_dead_letter",
)
DEAD_LETTER_CHECKPOINT_PATH = os.getenv(
    "DEAD_LETTER_CHECKPOINT_PATH",
    f"s3a://{MINIO_BUCKET}/checkpoints/orders_dead_letter",
)
RECONCILIATION_OUTPUT_PATH = os.getenv(
    "RECONCILIATION_OUTPUT_PATH",
    f"s3a://{MINIO_BUCKET}/streaming/orders_reconciliation",
)
RECONCILIATION_CHECKPOINT_PATH = os.getenv(
    "RECONCILIATION_CHECKPOINT_PATH",
    f"s3a://{MINIO_BUCKET}/checkpoints/orders_reconciliation",
)
POSTGRES_CHECKPOINT_PATH = os.getenv(
    "POSTGRES_CHECKPOINT_PATH",
    f"s3a://{MINIO_BUCKET}/checkpoints/orders_postgres",
)
KAFKA_FAIL_ON_DATA_LOSS = os.getenv(
    "KAFKA_FAIL_ON_DATA_LOSS",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}
KAFKA_MAX_OFFSETS_PER_TRIGGER = os.getenv("KAFKA_MAX_OFFSETS_PER_TRIGGER")
STREAMING_TRIGGER_SECONDS = int(os.getenv("STREAMING_TRIGGER_SECONDS", "10"))

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "de-demo-postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "dwh")
POSTGRES_USER = os.getenv("POSTGRES_USER", "app")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "app")

JDBC_URL = f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

POSTGRES_VERSION_GUARD = """
where excluded.business_version is not null
  and (
      marts.streaming_orders.business_version is null
      or excluded.business_version > marts.streaming_orders.business_version
  )
""".strip()

ORDER_SCHEMA = StructType(
    [
        StructField("order_id", StringType(), nullable=False),
        StructField("customer", StringType(), nullable=True),
        StructField("amount", DoubleType(), nullable=True),
        StructField("country", StringType(), nullable=True),
        StructField("status", StringType(), nullable=True),
        StructField("event_time", TimestampType(), nullable=True),
        StructField("business_version", LongType(), nullable=True),
    ]
)


def create_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("orders-realtime-pipeline")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
        .getOrCreate()
    )


def initialise_database() -> None:
    ddl = """
    create schema if not exists stg;
    create schema if not exists marts;

    create table if not exists marts.streaming_orders (
        order_id varchar primary key,
        customer varchar,
        amount numeric(14, 2),
        country varchar,
        status varchar,
        event_time timestamptz,
        kafka_timestamp timestamptz,
        kafka_partition integer,
        kafka_offset bigint,
        business_version bigint,
        batch_id bigint,
        updated_at timestamptz not null default now()
    );

    alter table marts.streaming_orders
        add column if not exists business_version bigint;

    create table if not exists marts.streaming_country_totals (
        country varchar primary key,
        orders_count bigint not null,
        total_amount numeric(18, 2) not null,
        avg_amount numeric(18, 2) not null,
        last_event_time timestamptz,
        refreshed_at timestamptz not null default now()
    );
    """

    with psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(ddl)


def upsert_postgres(batch_df: DataFrame, batch_id: int) -> None:
    if batch_df.isEmpty():
        return

    prepared_df = batch_df.select(
        "order_id",
        "customer",
        "amount",
        "country",
        "status",
        "event_time",
        "business_version",
        "kafka_timestamp",
        "kafka_partition",
        "kafka_offset",
    ).withColumn("batch_id", F.lit(batch_id))

    (
        prepared_df.write.format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", "stg.streaming_orders_batch")
        .option("user", POSTGRES_USER)
        .option("password", POSTGRES_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .mode("overwrite")
        .save()
    )

    merge_sql = f"""
    with deduped as (
        select
            order_id,
            customer,
            amount,
            country,
            status,
            event_time,
            business_version,
            kafka_timestamp,
            kafka_partition,
            kafka_offset,
            batch_id,
            row_number() over (
                partition by order_id
                order by business_version desc nulls last, kafka_offset desc
            ) as rn
        from stg.streaming_orders_batch
    )
    insert into marts.streaming_orders (
        order_id,
        customer,
        amount,
        country,
        status,
        event_time,
        business_version,
        kafka_timestamp,
        kafka_partition,
        kafka_offset,
        batch_id,
        updated_at
    )
    select
        order_id,
        customer,
        amount,
        country,
        status,
        event_time,
        business_version,
        kafka_timestamp,
        kafka_partition,
        kafka_offset,
        batch_id,
        now()
    from deduped
    where rn = 1
    on conflict (order_id) do update set
        customer = excluded.customer,
        amount = excluded.amount,
        country = excluded.country,
        status = excluded.status,
        event_time = excluded.event_time,
        business_version = excluded.business_version,
        kafka_timestamp = excluded.kafka_timestamp,
        kafka_partition = excluded.kafka_partition,
        kafka_offset = excluded.kafka_offset,
        batch_id = excluded.batch_id,
        updated_at = now()
    {POSTGRES_VERSION_GUARD};

    truncate table marts.streaming_country_totals;

    insert into marts.streaming_country_totals (
        country,
        orders_count,
        total_amount,
        avg_amount,
        last_event_time,
        refreshed_at
    )
    select
        coalesce(country, 'UNKNOWN'),
        count(*)::bigint,
        coalesce(sum(amount), 0)::numeric(18, 2),
        coalesce(avg(amount), 0)::numeric(18, 2),
        max(event_time),
        now()
    from marts.streaming_orders
    group by coalesce(country, 'UNKNOWN');
    """

    with psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(merge_sql)

    print(
        f"Completed PostgreSQL micro-batch "
        f"batch_id={batch_id}, rows={prepared_df.count()}"
    )


def write_reconciliation(batch_df: DataFrame, batch_id: int) -> None:
    """Persist one idempotent disposition count for every Kafka micro-batch."""

    counts = batch_df.agg(
        F.count(F.lit(1)).alias("observed_count"),
        F.coalesce(
            F.sum(
                F.when(F.col("dead_letter_reason").isNull(), 1).otherwise(0)
            ),
            F.lit(0),
        ).alias("valid_count"),
        F.coalesce(
            F.sum(
                F.when(F.col("dead_letter_reason").isNotNull(), 1).otherwise(0)
            ),
            F.lit(0),
        ).alias("dead_letter_count"),
        F.min("kafka_partition").alias("min_kafka_partition"),
        F.max("kafka_partition").alias("max_kafka_partition"),
        F.min("kafka_offset").alias("min_kafka_offset"),
        F.max("kafka_offset").alias("max_kafka_offset"),
    ).withColumn("batch_id", F.lit(batch_id))

    # The batch-id directory is overwritten on retry, so a retried micro-batch
    # cannot create a second reconciliation receipt.
    (
        counts.write.mode("overwrite")
        .parquet(f"{RECONCILIATION_OUTPUT_PATH}/batch_id={batch_id}")
    )


def main() -> None:
    initialise_database()
    spark = create_spark()

    spark.sparkContext.setLogLevel("WARN")

    kafka_reader = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", str(KAFKA_FAIL_ON_DATA_LOSS).lower())
    )
    if KAFKA_MAX_OFFSETS_PER_TRIGGER:
        kafka_reader = kafka_reader.option(
            "maxOffsetsPerTrigger",
            int(KAFKA_MAX_OFFSETS_PER_TRIGGER),
        )
    kafka_df = kafka_reader.load()

    classified_df = (
        kafka_df.select(
            F.col("value").cast("string").alias("raw_payload"),
            F.from_json(
                F.col("value").cast("string"),
                ORDER_SCHEMA,
            ).alias("order"),
            F.col("timestamp").alias("kafka_timestamp"),
            F.col("partition").alias("kafka_partition"),
            F.col("offset").alias("kafka_offset"),
        )
        .withColumn(
            "dead_letter_reason",
            F.when(F.col("order").isNull(), F.lit("invalid_json_or_schema"))
            .when(F.col("order.order_id").isNull(), F.lit("missing_order_id")),
        )
    )

    orders_df = (
        classified_df.filter(F.col("dead_letter_reason").isNull())
        .select(
            "order.*",
            "kafka_timestamp",
            "kafka_partition",
            "kafka_offset",
        )
        .withColumn("event_date", F.to_date("event_time"))
    )

    dead_letter_df = (
        classified_df.filter(F.col("dead_letter_reason").isNotNull())
        .select(
            "raw_payload",
            "dead_letter_reason",
            "kafka_timestamp",
            "kafka_partition",
            "kafka_offset",
        )
        .withColumn("dead_letter_date", F.to_date("kafka_timestamp"))
    )

    raw_query = (
        orders_df.writeStream.queryName("orders-raw-minio")
        .format("parquet")
        .outputMode("append")
        .partitionBy("event_date")
        .option("path", RAW_OUTPUT_PATH)
        .option("checkpointLocation", RAW_CHECKPOINT_PATH)
        .trigger(processingTime=f"{STREAMING_TRIGGER_SECONDS} seconds")
        .start()
    )

    postgres_query = (
        orders_df.drop("event_date")
        .writeStream.queryName("orders-postgres-upsert")
        .foreachBatch(upsert_postgres)
        .option("checkpointLocation", POSTGRES_CHECKPOINT_PATH)
        .trigger(processingTime=f"{STREAMING_TRIGGER_SECONDS} seconds")
        .start()
    )

    dead_letter_query = (
        dead_letter_df.writeStream.queryName("orders-dead-letter")
        .format("parquet")
        .outputMode("append")
        .partitionBy("dead_letter_date")
        .option("path", DEAD_LETTER_OUTPUT_PATH)
        .option("checkpointLocation", DEAD_LETTER_CHECKPOINT_PATH)
        .trigger(processingTime=f"{STREAMING_TRIGGER_SECONDS} seconds")
        .start()
    )

    reconciliation_query = (
        classified_df.writeStream.queryName("orders-reconciliation")
        .foreachBatch(write_reconciliation)
        .option("checkpointLocation", RECONCILIATION_CHECKPOINT_PATH)
        .trigger(processingTime=f"{STREAMING_TRIGGER_SECONDS} seconds")
        .start()
    )

    print(f"Raw MinIO query: {raw_query.id}")
    print(f"PostgreSQL query: {postgres_query.id}")
    print(f"Dead-letter query: {dead_letter_query.id}")
    print(f"Reconciliation query: {reconciliation_query.id}")
    print(f"Raw path: {RAW_OUTPUT_PATH}")
    print(f"Dead-letter path: {DEAD_LETTER_OUTPUT_PATH}")

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
