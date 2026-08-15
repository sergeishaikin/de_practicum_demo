FROM apache/superset@sha256:fb3464528ec7076f91195f0ff7835755aa023e281f1bb78a84782ce7a36b3705

USER root

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/
COPY superset/requirements.txt /tmp/requirements.txt
RUN /bin/uv pip install --python /app/.venv/bin/python --no-cache --require-hashes -r /tmp/requirements.txt

USER superset
