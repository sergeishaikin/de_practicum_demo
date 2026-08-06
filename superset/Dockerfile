FROM apache/superset:latest

USER root

RUN /app/.venv/bin/pip install --no-cache-dir \
    psycopg2-binary==2.9.10

USER superset