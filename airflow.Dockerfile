FROM apache/airflow:3.3.1-python3.12@sha256:b01a795dfbd113bbbfdf3ee169b8f27e9a0090ccef105f1a452b3594a11ed316

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/
COPY airflow.requirements.txt /tmp/requirements.txt

USER airflow

RUN /bin/uv pip install --no-cache --require-hashes -r /tmp/requirements.txt
