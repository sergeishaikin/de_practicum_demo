#!/usr/bin/env bash
set -euo pipefail

jar_list="$(find /opt/spark/h1-jars -type f -name '*.jar' -print | sort | paste -sd, -)"
if [ -z "$jar_list" ]; then
  echo "H1 Spark runtime JAR set is empty" >&2
  exit 64
fi

exec /opt/spark/bin/spark-submit --jars "$jar_list" "$@"
