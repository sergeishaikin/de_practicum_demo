FROM apache/airflow:2.9.3-python3.12@sha256:0188b06abb250caccc48bb6d00fde5e74a211273f78b0d143bc4d63f2b67412d

USER airflow

RUN pip install --no-cache-dir \
    psycopg2-binary==2.9.10 \
    trino==0.338.0
