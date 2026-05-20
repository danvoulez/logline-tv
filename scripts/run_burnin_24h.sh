#!/usr/bin/env bash
set -e

# Configurable parameters
DURATION_HOURS=${DURATION_HOURS:-24}
SAMPLE_EVERY_SEC=${SAMPLE_EVERY_SEC:-300}
RESTART_AT_HOUR=${RESTART_AT_HOUR:-6}

echo "=== 24h Burn-in Runner ==="
echo "Duration: ${DURATION_HOURS} hours"
echo "Sample interval: ${SAMPLE_EVERY_SEC} seconds"
echo "Streamer restart at hour: ${RESTART_AT_HOUR}"
echo "Start time: $(date -u)"
echo ""

# Initial probe
echo "Running initial probe..."
./scripts/burnin_probe.sh

# Calculate end time (using integer arithmetic)
END_TIME=$(($(date +%s) + DURATION_HOURS * 3600))
RESTART_TIME=$(($(date +%s) + RESTART_AT_HOUR * 3600))

# Main loop
while [ $(date +%s) -lt ${END_TIME} ]; do
  NOW=$(date +%s)

  # Check if it's time to restart streamer
  if [ ${NOW} -ge ${RESTART_TIME} ]; then
    echo "=== Restarting streamer at hour ${RESTART_AT_HOUR} ==="
    docker compose restart streamer
    sleep 30  # Give streamer time to recover

    # Verify HLS comes back
    echo "Verifying HLS recovery after restart..."
    for i in {1..10}; do
      HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/hls/stream.m3u8)
      if [ "${HTTP_CODE}" = "200" ]; then
        echo "HLS recovered after ${i} attempts"
        ./scripts/burnin_probe.sh
        break
      else
        echo "HLS not ready (HTTP ${HTTP_CODE}), attempt ${i}/10"
        sleep 10
      fi
    done

    RESTART_TIME=999999999999  # Prevent multiple restarts
  fi

  # Wait for next sample
  sleep ${SAMPLE_EVERY_SEC}

  # Run probe
  echo "Running probe at $(date -u)"
  ./scripts/burnin_probe.sh
done

echo "=== Burn-in Complete ==="
echo "End time: $(date -u)"
echo ""
echo "Final probe..."
./scripts/burnin_probe.sh
