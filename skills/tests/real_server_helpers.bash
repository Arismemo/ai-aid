# Boot real uvicorn per test. Slower than mock but catches mock/server drift.

setup() {
  TEST_TMP="$(mktemp -d)"
  PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')"
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  VENV_UV="$REPO_ROOT/server/.venv/bin/uvicorn"
  AI_AID_DB_PATH="$TEST_TMP/db.sqlite" \
    AI_AID_RATE_LIMIT_PER_MIN=10000 \
    bash -c "cd '$REPO_ROOT/server' && '$VENV_UV' ai_aid.main:create_app --factory --host 127.0.0.1 --port '$PORT' --log-level warning" \
      > "$TEST_TMP/srv.log" 2>&1 &
  SRV_PID=$!
  # Wait for ready (use the venv's uvicorn from server dir context)
  for _ in $(seq 1 40); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/health"; then
      break
    fi
    sleep 0.1
  done
  cat > "$TEST_TMP/cfg.json" <<EOF
{
  "server_url": "http://127.0.0.1:$PORT",
  "client_id": "bats-real-client",
  "model": "bats-model"
}
EOF
  export AI_AID_CONFIG="$TEST_TMP/cfg.json"
  export TEST_TMP PORT SRV_PID
  SCRIPTS_DIR="$REPO_ROOT/skills/shared/scripts"
  export SCRIPTS_DIR
}

teardown() {
  if [[ -n "${SRV_PID:-}" ]]; then
    kill "$SRV_PID" 2>/dev/null || true
    wait "$SRV_PID" 2>/dev/null || true
  fi
  if [[ -n "${TEST_TMP:-}" ]]; then
    rm -rf "$TEST_TMP"
  fi
}

# Run a script in another persona (different client_id)
run_as() {
  local who="$1"; shift
  local cfg="$TEST_TMP/cfg-$who.json"
  cat > "$cfg" <<EOF
{
  "server_url": "http://127.0.0.1:$PORT",
  "client_id": "$who",
  "model": "$who-model"
}
EOF
  AI_AID_CONFIG="$cfg" "$@"
}
