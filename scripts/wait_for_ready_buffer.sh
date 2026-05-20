#!/usr/bin/env bash
set -e

# Wait for ready buffer to reach threshold before starting stream
# Usage: ./scripts/wait_for_ready_buffer.sh [plan_id]

PLAN_ID="${1:-}"
API_BASE="${API_BASE:-http://localhost:8000}"
MIN_BUFFER_SEC="${MIN_BUFFER_SEC:-1800}"
TIMEOUT_SEC="${TIMEOUT_SEC:-1800}"
POLL_INTERVAL_SEC="${POLL_INTERVAL_SEC:-30}"

echo "=== Waiting for Ready Buffer ==="
echo "API base: ${API_BASE}"
echo "Min ready buffer: ${MIN_BUFFER_SEC} sec"
echo "Timeout: ${TIMEOUT_SEC} sec"
echo "Poll interval: ${POLL_INTERVAL_SEC} sec"
if [ -n "${PLAN_ID}" ]; then
  echo "Plan ID filter: ${PLAN_ID}"
fi
echo ""

START_TIME=$(date +%s)
END_TIME=$((START_TIME + TIMEOUT_SEC))

while true; do
  NOW=$(date +%s)
  if [ ${NOW} -ge ${END_TIME} ]; then
    echo "ERROR: Ready buffer timeout after ${TIMEOUT_SEC} seconds"
    echo "Current ready buffer: ${READY_BUFFER_SEC} sec (required: ${MIN_BUFFER_SEC} sec)"
    exit 1
  fi

  # Get ready buffer from observability snapshot
  if [ -n "${PLAN_ID}" ]; then
    # Filter by plan_id - need to query DB directly or use plan-specific endpoint
    # For now, use the general snapshot and note the plan_id
    OBS_JSON=$(curl -s "${API_BASE}/obs/snapshot")
  else
    OBS_JSON=$(curl -s "${API_BASE}/obs/snapshot")
  fi

  READY_BUFFER_SEC=$(echo "${OBS_JSON}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('pipeline', {}).get('ready_buffer_sec', 0))" 2>/dev/null || echo "0")
  READY_BUFFER_MIN=$(echo "${OBS_JSON}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('pipeline', {}).get('ready_buffer_min', 0))" 2>/dev/null || echo "0")
  READY_ITEMS=$(echo "${OBS_JSON}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('pipeline', {}).get('ready_items', 0))" 2>/dev/null || echo "0")
  QUEUED_ITEMS=$(echo "${OBS_JSON}" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('pipeline', {}).get('queued_items', 0))" 2>/dev/null || echo "0")

  ELAPSED=$((NOW - START_TIME))
  echo "[$(date -u)] Ready buffer: ${READY_BUFFER_SEC} sec (${READY_BUFFER_MIN} min) | Ready items: ${READY_ITEMS} | Queued: ${QUEUED_ITEMS} | Elapsed: ${ELAPSED}s"

  if [ "${READY_BUFFER_SEC}" -ge "${MIN_BUFFER_SEC}" ]; then
    echo ""
    echo "✓ Ready buffer threshold reached: ${READY_BUFFER_SEC} sec >= ${MIN_BUFFER_SEC} sec"
    echo "Ready to start stream."
    exit 0
  fi

  sleep ${POLL_INTERVAL_SEC}
done
