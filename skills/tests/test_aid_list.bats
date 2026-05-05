#!/usr/bin/env bats
load test_helpers

@test "aid-list: GETs /api/requests with status=open & exclude_client" {
  run bash "$SCRIPTS_DIR/aid_list.sh"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'"method":"GET"'* ]]
  [[ "$call" == *'status=open'* ]]
  [[ "$call" == *'exclude_client=test-client'* ]]
}
