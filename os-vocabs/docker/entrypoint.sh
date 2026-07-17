#!/usr/bin/env bash
set -euo pipefail

OS_URL="http://localhost:9200"
VOCABS_LIST="/data/vocabs.list"

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

# 3) Try loading each vocabulary, but DO NOT kill the container if something fails.
#    A failure for one vocabulary must not block the others.
#    We temporarily disable `-e` so curl failures don't exit the script.
set +e

load_vocab() {
  local vocab="$1"
  local alias="concepts_${vocab}"
  local index="concepts_${vocab}_v1"
  local data="/data/${vocab}/concepts.ndjson.gz"

  # If alias already exists, the vocabulary is loaded; skip (idempotent restarts)
  if curl -sf "$OS_URL/_alias/${alias}" >/dev/null 2>&1; then
    echo "[${vocab}] Alias '${alias}' already exists; skipping load."
    return 0
  fi

  echo "[${vocab}] Creating index ${index} with settings & mappings"
  curl -sf -X PUT "$OS_URL/${index}" \
    -H 'Content-Type: application/json' \
    --data-binary @/opt/os-config/settings.json
  if [ $? -ne 0 ]; then
    echo "[${vocab}] WARN: failed to create index settings; skipping bulk."
    return 1
  fi

  curl -sf -X PUT "$OS_URL/${index}/_mapping" \
    -H 'Content-Type: application/json' \
    --data-binary @/opt/os-config/mappings.body.json
  if [ $? -ne 0 ]; then
    echo "[${vocab}] WARN: failed to create index mapping."
  fi

  if [ -f "$data" ]; then
    echo "[${vocab}] Bulk loading ${data} → ${index}"
    gunzip -c "$data" | \
      awk '{print "{\"index\":{}}"; print $0}' | \
      curl -s -H 'Content-Type: application/x-ndjson' \
        -X POST "$OS_URL/${index}/_bulk" \
        --data-binary @- \
        -o "/tmp/bulk_result_${vocab}.json"

    if grep -q '"errors":true' "/tmp/bulk_result_${vocab}.json"; then
      echo "[${vocab}] WARN: bulk load reported errors (showing first ~2000 chars):"
      head -c 2000 "/tmp/bulk_result_${vocab}.json"; echo
    else
      echo "[${vocab}] Bulk load finished."
      curl -s -X POST "$OS_URL/${index}/_refresh" >/dev/null
    fi
  else
    echo "[${vocab}] WARN: ${data} not found; skipping bulk."
  fi

  echo "[${vocab}] Creating alias ${alias} -> ${index} (idempotent)"
  curl -s -X POST "$OS_URL/_aliases" \
    -H 'Content-Type: application/json' \
    -d "{\"actions\":[{\"add\":{\"index\":\"${index}\",\"alias\":\"${alias}\"}}]}" >/dev/null
}

if [ -f "$VOCABS_LIST" ]; then
  while IFS= read -r vocab; do
    [ -n "$vocab" ] || continue
    load_vocab "$vocab"
  done < "$VOCABS_LIST"
else
  echo "WARN: ${VOCABS_LIST} not found; no vocabulary to load."
fi

# Re-enable fail-fast after the loading block
set -e

# 4) Keep OpenSearch in the foreground
wait "$OS_PID"
