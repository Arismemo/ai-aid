# Common bats helpers — sourced via `load test_helpers` in each .bats file.

setup() {
  TEST_TMP="$(mktemp -d)"
  MOCK_PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')"
  python3 "$BATS_TEST_DIRNAME/mock_server.py" "$MOCK_PORT" \
    > "$TEST_TMP/mock.log" 2>"$TEST_TMP/mock.err" &
  MOCK_PID=$!
  # Wait until the server is listening
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s -o /dev/null "http://127.0.0.1:$MOCK_PORT/health"; then
      break
    fi
    sleep 0.1
  done
  cat > "$TEST_TMP/config.json" <<EOF
{
  "server_url": "http://127.0.0.1:$MOCK_PORT",
  "client_id": "test-client",
  "model": "test-model"
}
EOF
  export AI_AID_CONFIG="$TEST_TMP/config.json"
  export TEST_TMP MOCK_PORT MOCK_PID
  SCRIPTS_DIR="$(cd "$BATS_TEST_DIRNAME/../shared/scripts" && pwd)"
  export SCRIPTS_DIR
}

teardown() {
  if [[ -n "${MOCK_PID:-}" ]]; then
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
  fi
  if [[ -n "${TEST_TMP:-}" ]]; then
    rm -rf "$TEST_TMP"
  fi
}

# Read the latest JSON log line from the mock server
last_mock_call() {
  tail -n 1 "$TEST_TMP/mock.log"
}
