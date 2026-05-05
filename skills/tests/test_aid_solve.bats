#!/usr/bin/env bats
load test_helpers

@test "aid-solve: requires --id" {
  run bash "$SCRIPTS_DIR/aid_solve.sh" --summary "s"
  [ "$status" -ne 0 ]
  [[ "$output" == *"--id"* ]]
}

@test "aid-solve: posts to /api/requests/<id>/answers" {
  run bash "$SCRIPTS_DIR/aid_solve.sh" --id "abc-123" --summary "headline"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'/api/requests/abc-123/answers'* ]]
  [[ "$call" == *'"solver_client_id":"test-client"'* ]]
  [[ "$call" == *'"summary":"headline"'* ]]
}

@test "aid-solve: includes optional solution/reasoning/caveats" {
  run bash "$SCRIPTS_DIR/aid_solve.sh" --id "abc" --summary "s" \
    --solution "code" --reasoning "why" --caveats "but"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'"solution":"code"'* ]]
  [[ "$call" == *'"reasoning":"why"'* ]]
  [[ "$call" == *'"caveats":"but"'* ]]
}
