FROM apache/spark:4.2.0-java21-python3

USER root

RUN python3 -m pip install --no-cache-dir \
    psycopg2-binary==2.9.10 \
    boto3==1.35.99

ENV PYSPARK_PYTHON=/usr/bin/python3

USER spark