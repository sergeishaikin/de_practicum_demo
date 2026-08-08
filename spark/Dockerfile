FROM apache/spark:4.2.0-java21-python3

USER root

RUN python3 -m pip install --no-cache-dir \
    psycopg2-binary==2.9.10 \
    boto3==1.35.99 \
    prometheus-client==0.22.1

ENV PYSPARK_PYTHON=/usr/bin/python3

# Pre-create the Ivy cache dir owned by `spark` (uid 185). Docker seeds an empty
# named volume from the image path, ownership included; without this the
# de_demo_spark_ivy_cache mount lands as root:root and spark-submit cannot
# write its resolution cache.
RUN mkdir -p /tmp/spark-ivy/cache /tmp/spark-ivy/jars \
    && chown -R spark:spark /tmp/spark-ivy

USER spark
