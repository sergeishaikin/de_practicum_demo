FROM quay.io/jupyter/base-notebook@sha256:8201703b74c5f05068a9d1d4a2e542dd67833d749502f197ec8346547cc2d9e6

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openjdk-21-jre-headless \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER ${NB_UID}

RUN mamba create -y -n spark420 \
        python=3.10 \
        ipykernel \
        pip \
    && mamba clean --all -f -y

RUN /opt/conda/envs/spark420/bin/python -m pip install --no-cache-dir \
        "pyspark[connect]==4.2.0" \
        "pandas==2.2.3" \
        "pyarrow==21.0.0" \
        psycopg2-binary==2.9.10 \
        boto3==1.35.99

RUN /opt/conda/envs/spark420/bin/python -m ipykernel install \
        --user \
        --name spark420 \
        --display-name "Spark 4.2.0 / Python 3.10"
