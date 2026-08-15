FROM apache/airflow:2.9.3-python3.12@sha256:0188b06abb250caccc48bb6d00fde5e74a211273f78b0d143bc4d63f2b67412d

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/
COPY airflow.requirements.txt /tmp/requirements.txt

USER airflow

RUN /bin/uv pip install --no-cache --require-hashes -r /tmp/requirements.txt
