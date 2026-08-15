FROM quay.io/jupyter/base-notebook@sha256:8201703b74c5f05068a9d1d4a2e542dd67833d749502f197ec8346547cc2d9e6

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openjdk-21-jre-headless \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER ${NB_UID}

COPY --chown=${NB_UID}:${NB_GID} requirements.txt /tmp/requirements.txt
RUN /bin/uv python install 3.10.21 \
    && /bin/uv venv --python 3.10.21 /opt/conda/envs/spark420 \
    && /bin/uv pip install --python /opt/conda/envs/spark420/bin/python \
        --no-cache \
        --require-hashes \
        -r /tmp/requirements.txt

RUN /opt/conda/envs/spark420/bin/python -m ipykernel install \
        --user \
        --name spark420 \
        --display-name "Spark 4.2.0 / Python 3.10"
