#!/usr/bin/env bash
set -euo pipefail

# The H1 runtime JARs are baked into this image, so every driver and executor
# already has them at the same path. Prefixing each with `local:` tells Spark the
# file is pre-deployed and must not be distributed: without it Spark stages the
# whole 678 MB set (612 MB of which is the AWS SDK bundle) into a fresh
# /opt/spark/work/app-*/ directory on the worker for *every* submission, which is
# what filled the Docker disk on 2026-08-16.
jar_list="$(find /opt/spark/h1-jars -type f -name '*.jar' -print | sort | sed 's|^|local:|' | paste -sd, -)"
if [ -z "$jar_list" ]; then
  echo "H1 Spark runtime JAR set is empty" >&2
  exit 64
fi

exec /opt/spark/bin/spark-submit --jars "$jar_list" "$@"
