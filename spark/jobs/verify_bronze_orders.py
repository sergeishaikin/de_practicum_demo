from __future__ import annotations

import sys

from pyspark.sql import SparkSession


TABLE = "iceberg.bronze.orders"


def main() -> None:
    spark = (
        SparkSession.builder
        .appName("verify-bronze-orders")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print("== Tables in iceberg.bronze ==")
    for row in spark.sql("show tables in iceberg.bronze").collect():
        print(row.asDict())

    print("\n== bronze.orders schema ==")
    for row in spark.sql(f"describe extended {TABLE}").collect():
        name = row["col_name"]
        if name in ("", "# Partitioning", "Part 0", "Spec Order 0"):
            continue
        print(f"{name}: {row['data_type']}")

    current_count = spark.sql(f"select count(*) as c from {TABLE}").collect()[0].c
    print(f"\nCurrent row count: {current_count}")

    snapshots = (
        spark.sql(
            f"select committed_at, snapshot_id, summary['added-records'] as added_records "
            f"from {TABLE}.snapshots order by committed_at"
        )
        .collect()
    )
    print(f"\nSnapshot count: {len(snapshots)}")
    for row in snapshots:
        print(
            f"  committed_at={row.committed_at} snapshot_id={row.snapshot_id} "
            f"added_records={row.added_records}"
        )

    if len(snapshots) >= 2:
        earliest_id = snapshots[0].snapshot_id
        early_count = (
            spark.sql(
                f"select count(*) as c from {TABLE} version as of {earliest_id}"
            )
            .collect()[0]
            .c
        )
        print(
            f"\nTime travel: at snapshot {earliest_id} rows={early_count}, "
            f"current rows={current_count} (delta {current_count - early_count})"
        )

    spark.stop()


if __name__ == "__main__":
    sys.exit(main())
