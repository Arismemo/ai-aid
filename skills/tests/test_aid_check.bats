#!/usr/bin/env bats
load test_helpers

@test "aid-check: GETs /api/requests/<id>" {
  run bash "$SCRIPTS_DIR/aid_check.sh" "some-id"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'/api/requests/some-id'* ]]
}

@test "aid-check: requires id arg" {
  run bash "$SCRIPTS_DIR/aid_check.sh"
  [ "$status" -ne 0 ]
}
