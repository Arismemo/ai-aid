#!/usr/bin/env bats
load test_helpers

@test "aid-ask: posts to /api/requests with all required fields" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'"method":"POST"'* ]]
  [[ "$call" == *'/api/requests'* ]]
  [[ "$call" == *'"client_id":"test-client"'* ]]
  [[ "$call" == *'"goal":"g"'* ]]
}

@test "aid-ask: omits empty optional fields from payload" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  # error and constraints should NOT appear in payload (jq select drops empty strings)
  body="$(echo "$call" | jq -r '.body')"
  [[ "$body" != *"\"error\""* ]] || [[ "$body" == *"\"error\":null"* ]]
}

@test "aid-ask: includes optional fields when provided" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q" \
    --error "boom" --constraints "no foo"
  [ "$status" -eq 0 ]
  call="$(last_mock_call)"
  [[ "$call" == *'"error":"boom"'* ]]
  [[ "$call" == *'"constraints":"no foo"'* ]]
}

@test "aid-ask: exits 1 on server 4xx (mock returns 400 for empty goal)" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" --json '{"goal":"","client_id":"x","model":"y","context":"c","tried":"t","question":"q"}'
  [ "$status" -ne 0 ]
}
