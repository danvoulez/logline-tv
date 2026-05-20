#!/usr/bin/env bash

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
REPORT_DIR="./burnin_reports"
REPORT_FILE="${REPORT_DIR}/burnin_$(date +%Y%m%d).log"

mkdir -p "${REPORT_DIR}"

echo "=== Burn-in Probe: ${TIMESTAMP} ===" >> "${REPORT_FILE}"

# docker compose ps
echo "--- Docker Compose PS ---" >> "${REPORT_FILE}"
docker compose ps >> "${REPORT_FILE}" 2>&1

# /health
echo "--- API Health ---" >> "${REPORT_FILE}"
curl -s http://localhost:8000/health >> "${REPORT_FILE}" 2>&1

# /obs/snapshot
echo "--- Observability Snapshot ---" >> "${REPORT_FILE}"
curl -s http://localhost:8000/obs/snapshot >> "${REPORT_FILE}" 2>&1

# HLS playlist HTTP status + content-type
echo "--- HLS Playlist ---" >> "${REPORT_FILE}"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\nContent-Type: %{content_type}\n" http://localhost:8000/hls/stream.m3u8 >> "${REPORT_FILE}" 2>&1

# first/current segment HTTP status + content-type
echo "--- First Segment ---" >> "${REPORT_FILE}"
FIRST_SEG=$(curl -s http://localhost:8000/hls/stream.m3u8 | grep -E "^[^#].*\.ts$" | head -1)
if [ -n "${FIRST_SEG}" ]; then
  curl -s -o /dev/null -w "HTTP Status: %{http_code}\nContent-Type: %{content_type}\n" "http://localhost:8000/hls/${FIRST_SEG}" >> "${REPORT_FILE}" 2>&1
else
  echo "No segment found in playlist" >> "${REPORT_FILE}"
fi

# HLS segment count
echo "--- HLS Segment Count ---" >> "${REPORT_FILE}"
docker exec logline-tv-api-1 sh -lc "ls /spool/hls/*.ts 2>/dev/null | wc -l" >> "${REPORT_FILE}" 2>&1

# HLS directory size
echo "--- HLS Directory Size ---" >> "${REPORT_FILE}"
docker exec logline-tv-api-1 sh -lc "du -sh /spool/hls" >> "${REPORT_FILE}" 2>&1

# disk usage for /spool
echo "--- Spool Disk Usage ---" >> "${REPORT_FILE}"
docker exec logline-tv-api-1 sh -lc "du -sh /spool" >> "${REPORT_FILE}" 2>&1

# stream_control row
echo "--- Stream Control ---" >> "${REPORT_FILE}"
docker exec logline-tv-db-1 psql -U postgres -d voulezvous -c "SELECT * FROM stream_control ORDER BY updated_at DESC LIMIT 1;" >> "${REPORT_FILE}" 2>&1

# last 20 stream_events
echo "--- Last 20 Stream Events ---" >> "${REPORT_FILE}"
docker exec logline-tv-db-1 psql -U postgres -d voulezvous -c "SELECT event_type, plan_id, plan_item_id, asset_id, occurred_at FROM stream_events ORDER BY occurred_at DESC LIMIT 20;" >> "${REPORT_FILE}" 2>&1

# item_started/item_completed/item_failed counts
echo "--- Stream Plan Item Status Counts ---" >> "${REPORT_FILE}"
docker exec logline-tv-db-1 psql -U postgres -d voulezvous -c "SELECT stream_status, COUNT(*) FROM stream_plan_items GROUP BY stream_status ORDER BY stream_status;" >> "${REPORT_FILE}" 2>&1

# latest streamer logs tail
echo "--- Streamer Logs (last 50 lines) ---" >> "${REPORT_FILE}"
docker compose logs streamer --tail 50 >> "${REPORT_FILE}" 2>&1

# latest prep-worker logs tail
echo "--- Prep Worker Logs (last 50 lines) ---" >> "${REPORT_FILE}"
docker compose logs prep-worker --tail 50 >> "${REPORT_FILE}" 2>&1

echo "" >> "${REPORT_FILE}"
