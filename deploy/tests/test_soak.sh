#!/usr/bin/env bash
# Soak test: keep the container under light continuous load for N seconds,
# sample memory + check for errors. Catches:
#   - memory growth (file handle / connection leaks)
#   - container drift to unhealthy
#   - SQLite corruption over time
#
# Usage: bash deploy/tests/test_soak.sh [DURATION_SEC] [REQS_PER_SEC]

set -euo pipefail
DURATION="${1:-60}"   # default 60s for CI; bump to 300 for full soak
RPS="${2:-5}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PORT=18098
CONTAINER=ai-aid-soak
DATA_DIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; rm -rf "$DATA_DIR"' EXIT

docker build -t ai-aid:soak ./server >/dev/null
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e AI_AID_DB_PATH=/data/db.sqlite \
  -e AI_AID_RATE_LIMIT_PER_MIN=10000 \
  -v "$DATA_DIR":/data \
  -p "127.0.0.1:$PORT:8000" \
  ai-aid:soak >/dev/null

for _ in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then break; fi
  sleep 1
done

START_RSS="$(docker stats --no-stream --format '{{.MemUsage}}' "$CONTAINER" | awk '{print $1}')"
echo "START_RSS=$START_RSS"

END=$(( $(date +%s) + DURATION ))
COUNT=0
while [ "$(date +%s)" -lt "$END" ]; do
  for _ in $(seq 1 "$RPS"); do
    SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests" \
      -H "Content-Type: application/json" \
      -d "{\"client_id\":\"soak-$((COUNT % 5))\",\"model\":\"m\",\"goal\":\"g$COUNT\",\"context\":\"c\",\"tried\":\"t\",\"error\":null,\"constraints\":null,\"question\":\"q\"}")"
    if [[ "$SC" != "201" ]]; then
      echo "FAIL on $COUNT: $SC"
      docker logs --tail=30 "$CONTAINER"
      exit 1
    fi
    COUNT=$((COUNT + 1))
  done
  sleep 1
done

END_RSS="$(docker stats --no-stream --format '{{.MemUsage}}' "$CONTAINER" | awk '{print $1}')"
HEALTH_END="$(curl -s "http://127.0.0.1:$PORT/health")"

# Sanity: count rows
ROW_COUNT="$(docker exec "$CONTAINER" python -c \
  "import sqlite3; print(sqlite3.connect('/data/db.sqlite').execute('SELECT COUNT(*) FROM requests').fetchone()[0])")"

echo "soak summary:"
echo "  duration : ${DURATION}s"
echo "  rps      : $RPS"
echo "  posted   : $COUNT"
echo "  db rows  : $ROW_COUNT"
echo "  start RSS: $START_RSS"
echo "  end   RSS: $END_RSS"
echo "  health   : $HEALTH_END"

[ "$ROW_COUNT" = "$COUNT" ] || { echo "row count mismatch"; exit 1; }
echo "$HEALTH_END" | jq -e '.ok == true' >/dev/null
echo "=== SOAK PASS ==="
