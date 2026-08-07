FROM apache/airflow:2.9.3-python3.12

USER airflow

RUN pip install --no-cache-dir psycopg2-binary==2.9.9 trino==0.329.0
