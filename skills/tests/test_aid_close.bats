#!/usr/bin/env bats
load test_helpers

@test "aid-close: POSTs to /api/requests/<id>/close" {
  run bash "$SCRIPTS_DIR/aid_close.sh" "rid-99"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'/api/requests/rid-99/close'* ]]
  [[ "$call" == *'"method":"POST"'* ]]
}

@test "aid-close: requires id arg" {
  run bash "$SCRIPTS_DIR/aid_close.sh"
  [ "$status" -ne 0 ]
}
