#!/usr/bin/env bash
set -euo pipefail

: "${TRINO_S3_ACCESS_KEY:?TRINO_S3_ACCESS_KEY is required}"
: "${TRINO_S3_SECRET_KEY:?TRINO_S3_SECRET_KEY is required}"

TEMPLATE=/etc/trino/catalog/iceberg.properties.template
TARGET=/etc/trino/catalog/iceberg.properties

sed \
  -e "s|{{S3_ACCESS_KEY}}|${TRINO_S3_ACCESS_KEY}|g" \
  -e "s|{{S3_SECRET_KEY}}|${TRINO_S3_SECRET_KEY}|g" \
  "$TEMPLATE" > "$TARGET"

echo "start-trino: generated $TARGET from template"
exec /usr/lib/trino/bin/run-trino
