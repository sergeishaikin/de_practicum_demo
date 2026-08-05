import os
from pyspark.sql import SparkSession, functions as F

spark = (
    SparkSession.builder
    .appName("build-sales-mart")
    .master(os.getenv("SPARK_MASTER", "spark://spark-master:7077"))
    .config("spark.jars.packages", "org.postgresql:postgresql:42.7.4")
    .getOrCreate()
)

jdbc_url = f"jdbc:postgresql://{os.getenv('DWH_HOST', 'postgres')}:5432/{os.getenv('DWH_DB', 'dwh')}"
props = {
    "user": os.getenv("DWH_USER", "app"),
    "password": os.getenv("DWH_PASSWORD", "app"),
    "driver": "org.postgresql.Driver",
}

orders = spark.read.jdbc(jdbc_url, "raw.orders", properties=props)
mart = (
    orders.withColumn("sales_date", F.to_date("order_ts"))
    .groupBy("sales_date")
    .agg(F.countDistinct("order_id").alias("orders_count"), F.sum("amount").alias("revenue"))
)
mart.write.mode("overwrite").jdbc(jdbc_url, "marts.sales_daily", properties=props)
spark.stop()
