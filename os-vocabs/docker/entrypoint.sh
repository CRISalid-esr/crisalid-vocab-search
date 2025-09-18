#!/usr/bin/env bash
set -euo pipefail

OS_URL="http://localhost:9200"

# 1) Start OpenSearch (OS3 image ships this path)
#    Capture PID so we can keep the container alive.
# shellcheck disable=SC2086
/usr/share/opensearch/opensearch-docker-entrypoint.sh &
OS_PID=$!

# 2) Wait for OpenSearch HTTP to come up (max ~90s, but continue to wait longer for cluster green)
for i in {1..90}; do
  if curl -s "$OS_URL" >/dev/null 2>&1; then
    break
  fi
  echo "Waiting for OpenSearch..."
  sleep 1
done

# 3) Try loading index + data, but DO NOT kill the container if something fails.
#    We temporarily disable `-e` so curl failures don't exit the script.
set +e

# If alias is missing, (re)create index and load
curl -sf "$OS_URL/_alias/concepts" >/dev/null 2>&1
ALIAS_EXISTS=$?
if [ "$ALIAS_EXISTS" -ne 0 ]; then
  echo "Creating index concepts_v1 with settings & mappings"
# settings
curl -sS -o /tmp/create_index.json -w "%{http_code}" \
  -H 'Content-Type: application/json' -X PUT "$OS_URL/concepts_v1" \
  --data-binary @/opt/os-config/settings.json | grep -qE '^(200|201)$' \
  || grep -q 'resource_already_exists_exception' /tmp/create_index.json

CREATE_SETTINGS_RC=$?  # 0 means ok or already exists

# mapping
curl -sS -o /tmp/put_mapping.json -w "%{http_code}" \
  -H 'Content-Type: application/json' -X PUT "$OS_URL/concepts_v1/_mapping" \
  --data-binary @/opt/os-config/mappings.body.json | grep -qE '^(200|201)$'
CREATE_MAPPING_RC=$?

if [ "$CREATE_SETTINGS_RC" -ne 0 ] || [ "$CREATE_MAPPING_RC" -ne 0 ]; then
  echo "WARN: failed to create index settings/mapping; skipping bulk."
  exit 0
fi
else
  if [ -f /data/concepts.ndjson.gz ]; then
    echo "Bulk loading /data/concepts.ndjson.gz → concepts_v1"
    gunzip -c /data/concepts.ndjson.gz | \
      awk '{print "{\"index\":{}}"; print $0}' | \
      curl -s -H 'Content-Type: application/x-ndjson' \
        -X POST "$OS_URL/concepts_v1/_bulk" \
        --data-binary @- \
        -o /tmp/bulk_result.json

    if grep -q '"errors":true' /tmp/bulk_result.json; then
      echo "WARN: bulk load reported errors (showing first ~2000 chars):"
      head -c 2000 /tmp/bulk_result.json; echo
    else
      echo "Bulk load finished."
      curl -s -X POST "$OS_URL/concepts_v1/_refresh" >/dev/null
    fi
  else
    echo "WARN: /data/concepts.ndjson.gz not found; skipping bulk."
  fi

  echo "Creating alias concepts -> concepts_v1 (idempotent)"
  curl -s -X POST "$OS_URL/_aliases" \
    -H 'Content-Type: application/json' \
    -d '{"actions":[{"add":{"index":"concepts_v1","alias":"concepts"}}]}' >/dev/null
fi


else
  echo "Alias 'concepts' already exists; skipping load."
fi

# Re-enable fail-fast after the loading block
set -e

# 4) Keep OpenSearch in the foreground
wait "$OS_PID"
