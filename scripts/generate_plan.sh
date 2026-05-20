#!/usr/bin/env bash
set -e

# Generate a single plan and capture PLAN_ID
# Usage: ./scripts/generate_plan.sh [hours]

HOURS="${1:-24}"
PLAN_DATE="${PLAN_DATE:-$(date +%Y-%m-%d)}"
API_BASE="${API_BASE:-http://localhost:8000}"

echo "=== Generating Plan ==="
echo "Plan date: ${PLAN_DATE}"
echo "Duration: ${HOURS} hours"
echo "API base: ${API_BASE}"
echo ""

# Generate plan and capture PLAN_ID
PLAN_JSON=$(curl -s -X POST "${API_BASE}/plans/generate" \
  -H "Content-Type: application/json" \
  -d "{\"plan_date\": \"${PLAN_DATE}\", \"hours\": ${HOURS}, \"mix_music\": false}")
PLAN_ID=$(echo "${PLAN_JSON}" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

if [ -z "${PLAN_ID}" ]; then
  echo "ERROR: Failed to generate plan or extract PLAN_ID"
  echo "Response: ${PLAN_JSON}"
  exit 1
fi

echo "✓ Plan generated: ${PLAN_ID}"
echo "Export PLAN_ID for use in burn-in:"
echo "  export PLAN_ID=${PLAN_ID}"
echo ""

# Output PLAN_ID for capture
echo "${PLAN_ID}"
