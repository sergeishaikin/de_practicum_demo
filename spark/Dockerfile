FROM apache/spark:4.2.0-java21-python3@sha256:fc64959c04bd87b0ac686be9aaa9008b69cdb1afc695400528279c8b01f43d89

USER root

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYSPARK_PYTHON=/usr/bin/python3

COPY h1-runtime-jars.lock /tmp/h1-runtime-jars.lock
COPY submit-with-runtime.sh /usr/local/bin/spark-submit-h1
RUN set -eu \
    && chmod +x /usr/local/bin/spark-submit-h1 \
    && mkdir -p /opt/spark/h1-jars \
    && while IFS='|' read -r group artifact version; do \
         case "$group" in ''|'#'*) continue ;; esac; \
         group_path="$(printf '%s' "$group" | tr '.' '/')"; \
         path="${group_path}/${artifact}/${version}/${artifact}-${version}.jar"; \
         curl --fail --silent --show-error --location --retry 4 \
           "https://repo1.maven.org/maven2/${path}" \
           --output "/opt/spark/h1-jars/${artifact}-${version}.jar"; \
       done < /tmp/h1-runtime-jars.lock \
    && chown -R spark:spark /opt/spark/h1-jars /usr/local/bin/spark-submit-h1

USER spark
