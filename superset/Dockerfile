FROM apache/superset@sha256:fb3464528ec7076f91195f0ff7835755aa023e281f1bb78a84782ce7a36b3705

USER root

RUN /app/.venv/bin/pip install --no-cache-dir \
    psycopg2-binary==2.9.10

USER superset
