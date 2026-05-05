#!/usr/bin/env bats
load real_server_helpers

@test "real: aid_ask + aid_check round-trip" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "real test" --context "ctx" --tried "x" --question "y"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"
  [ -n "$rid" ]

  run bash "$SCRIPTS_DIR/aid_check.sh" "$rid"
  [ "$status" -eq 0 ]
  [[ "$output" == *"\"id\":\"$rid\""* ]]
  [[ "$output" == *"\"answers\":[]"* ]]
}

@test "real: aid_solve different client succeeds; same client 403s" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"

  # Self-solve: 4xx → script exits non-zero
  run bash "$SCRIPTS_DIR/aid_solve.sh" --id "$rid" --summary "self"
  [ "$status" -ne 0 ]

  # Other persona: 201
  run run_as "other-helper" bash "$SCRIPTS_DIR/aid_solve.sh" --id "$rid" --summary "from other"
  [ "$status" -eq 0 ]

  # Check shows the answer
  run bash "$SCRIPTS_DIR/aid_check.sh" "$rid"
  [ "$status" -eq 0 ]
  [[ "$output" == *"from other"* ]]
}

@test "real: aid_list excludes own requests" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "mine" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]

  run bash "$SCRIPTS_DIR/aid_list.sh"
  [ "$status" -eq 0 ]
  # The list excludes self, so should NOT contain "bats-real-client"
  [[ "$output" != *"\"client_id\":\"bats-real-client\""* ]]
}

@test "real: aid_mine includes own + closed" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"
  run bash "$SCRIPTS_DIR/aid_close.sh" "$rid"
  [ "$status" -eq 0 ]

  run bash "$SCRIPTS_DIR/aid_mine.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"\"id\":\"$rid\""* ]]
  [[ "$output" == *"\"status\":\"closed\""* ]]
}

@test "real: optional fields in ask round-trip correctly" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q" \
    --error "boom!" --constraints "no foo"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"

  run bash "$SCRIPTS_DIR/aid_check.sh" "$rid"
  [[ "$output" == *"\"error\":\"boom!\""* ]]
  [[ "$output" == *"\"constraints\":\"no foo\""* ]]
}
