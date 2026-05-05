#!/usr/bin/env bats
load test_helpers

@test "aid-mine: GETs with mine=1 + own client_id + status=all" {
  run bash "$SCRIPTS_DIR/aid_mine.sh"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'mine=1'* ]]
  [[ "$call" == *'client_id=test-client'* ]]
  [[ "$call" == *'status=all'* ]]
}
