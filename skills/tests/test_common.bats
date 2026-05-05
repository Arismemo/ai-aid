#!/usr/bin/env bats
load test_helpers

@test "_common: exits with config error if AI_AID_CONFIG missing" {
  unset AI_AID_CONFIG
  run bash "$SCRIPTS_DIR/aid_list.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"config not found"* ]]
}

@test "_common: errors on missing server_url" {
  cat > "$TEST_TMP/bad.json" <<EOF
{"server_url": "", "client_id": "c", "model": "m"}
EOF
  AI_AID_CONFIG="$TEST_TMP/bad.json" run bash "$SCRIPTS_DIR/aid_list.sh"
  [ "$status" -ne 0 ]
  [[ "$output" == *"server_url"* ]]
}

@test "_common: success exits 0" {
  run bash "$SCRIPTS_DIR/aid_list.sh"
  [ "$status" -eq 0 ]
}
