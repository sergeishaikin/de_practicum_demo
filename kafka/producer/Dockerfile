FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN /bin/uv pip install --system --no-cache --require-hashes -r /tmp/requirements.txt
COPY orders_producer.py /app/orders_producer.py

ENTRYPOINT ["python", "/app/orders_producer.py"]
