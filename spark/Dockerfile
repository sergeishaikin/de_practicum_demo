FROM apache/spark:4.2.0-java21-python3@sha256:fc64959c04bd87b0ac686be9aaa9008b69cdb1afc695400528279c8b01f43d89

USER root

COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/
COPY requirements.txt /tmp/requirements.txt
RUN /bin/uv pip install --python /usr/bin/python3 --no-cache --require-hashes -r /tmp/requirements.txt

ENV PYSPARK_PYTHON=/usr/bin/python3

COPY h1-runtime-jars.lock /tmp/h1-runtime-jars.lock
RUN set -eu \
    && mkdir -p /opt/spark/h1-jars \
    && while IFS='|' read -r group artifact version; do \
         case "$group" in ''|'#'*) continue ;; esac; \
         group_path="$(printf '%s' "$group" | tr '.' '/')"; \
         path="${group_path}/${artifact}/${version}/${artifact}-${version}.jar"; \
         curl --fail --silent --show-error --location --retry 4 \
           "https://repo1.maven.org/maven2/${path}" \
           --output "/opt/spark/h1-jars/${artifact}-${version}.jar"; \
       done < /tmp/h1-runtime-jars.lock \
    && chown -R spark:spark /opt/spark/h1-jars

# Copied *after* the JAR download so that editing the wrapper does not
# invalidate the 678 MB download layer. The submit wrapper changes far more
# often than the pinned JAR set does.
COPY submit-with-runtime.sh /usr/local/bin/spark-submit-h1
RUN chmod +x /usr/local/bin/spark-submit-h1 \
    && chown spark:spark /usr/local/bin/spark-submit-h1

USER spark
