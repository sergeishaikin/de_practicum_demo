FROM python:3.12-slim

RUN pip install --no-cache-dir \
    psycopg2-binary==2.9.10 \
    prometheus-client==0.22.1

WORKDIR /app
COPY postgres_exporter.py /app/postgres_exporter.py

CMD ["python", "/app/postgres_exporter.py"]
