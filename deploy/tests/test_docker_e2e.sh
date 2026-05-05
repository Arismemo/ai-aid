#!/usr/bin/env bash
# End-to-end docker container test:
#   - build image
#   - run container with mounted data + web
#   - hit /health, post requests, list, solve, check, close
#   - verify container has web mount + db survives restart
#
# Usage: bash deploy/tests/test_docker_e2e.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PORT=18099
CONTAINER=ai-aid-e2e
DATA_DIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; rm -rf "$DATA_DIR"' EXIT

echo "=== build ==="
docker build -t ai-aid:e2e ./server >/dev/null

echo "=== run container ==="
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e AI_AID_DB_PATH=/data/ai-aid.db \
  -e AI_AID_RATE_LIMIT_PER_MIN=10000 \
  -v "$DATA_DIR":/data \
  -v "$REPO_ROOT/web":/web:ro \
  -p "127.0.0.1:$PORT:8000" \
  ai-aid:e2e >/dev/null

echo "=== wait healthy ==="
for _ in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then
    break
  fi
  sleep 1
done
H="$(curl -s "http://127.0.0.1:$PORT/health")"
echo "health: $H"
echo "$H" | jq -e '.ok == true' >/dev/null

echo "=== / serves dashboard ==="
INDEX="$(curl -s "http://127.0.0.1:$PORT/")"
[[ "$INDEX" == *"ai-aid Dashboard"* ]] || { echo "/ missing dashboard"; exit 1; }
JS_OK="$(curl -s "http://127.0.0.1:$PORT/web/app.js" | grep -c "EventSource")"
[[ "$JS_OK" -gt 0 ]] || { echo "app.js missing"; exit 1; }

echo "=== ask + check + solve + close ==="
RID="$(curl -s -X POST "http://127.0.0.1:$PORT/api/requests" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"docker-asker","model":"m","goal":"docker e2e","context":"c","tried":"t","question":"q"}' \
  | jq -r .id)"
[ -n "$RID" ] && [ "$RID" != "null" ]

curl -s "http://127.0.0.1:$PORT/api/requests/$RID" \
  | jq -e '.goal == "docker e2e"' >/dev/null

# Self-solve must 403
SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests/$RID/answers" \
  -H "Content-Type: application/json" \
  -d '{"solver_client_id":"docker-asker","solver_model":"m","summary":"self"}')"
[ "$SC" = "403" ] || { echo "self-solve expected 403, got $SC"; exit 1; }

# Other solver: 201
SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests/$RID/answers" \
  -H "Content-Type: application/json" \
  -d '{"solver_client_id":"docker-solver","solver_model":"m","summary":"hi"}')"
[ "$SC" = "201" ] || { echo "solve expected 201, got $SC"; exit 1; }

# Close
SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests/$RID/close")"
[ "$SC" = "200" ] || { echo "close expected 200, got $SC"; exit 1; }

echo "=== restart preserves data ==="
docker restart "$CONTAINER" >/dev/null
for _ in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then
    break
  fi
  sleep 1
done
STATUS_AFTER="$(curl -s "http://127.0.0.1:$PORT/api/requests/$RID" | jq -r .status)"
[ "$STATUS_AFTER" = "closed" ] || { echo "post-restart status mismatch: $STATUS_AFTER"; exit 1; }

echo "=== SSE stream delivers ==="
(curl -s -N "http://127.0.0.1:$PORT/events?last_event_id=0&max_seconds=2" > "$DATA_DIR/sse.txt") &
SSE_PID=$!
sleep 0.3
curl -s -o /dev/null -X POST "http://127.0.0.1:$PORT/api/requests" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"sse-test","model":"m","goal":"sse","context":"c","tried":"t","question":"q"}'
wait "$SSE_PID"
[ "$(grep -c 'request.created' "$DATA_DIR/sse.txt")" -gt 0 ] \
  || { echo "no SSE event delivered"; cat "$DATA_DIR/sse.txt"; exit 1; }

echo "=== ALL DOCKER E2E PASS ==="
