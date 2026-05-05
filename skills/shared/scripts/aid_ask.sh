#!/usr/bin/env bash
# Post a new help request.
#
# Usage: aid_ask.sh --goal G --context C --tried T --question Q [--error E] [--constraints K]
#        aid_ask.sh --json '{...}'   # raw JSON body bypass

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

GOAL=""; CONTEXT=""; TRIED=""; QUESTION=""; ERROR=""; CONSTRAINTS=""; RAW=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --goal) GOAL="$2"; shift 2;;
    --context) CONTEXT="$2"; shift 2;;
    --tried) TRIED="$2"; shift 2;;
    --question) QUESTION="$2"; shift 2;;
    --error) ERROR="$2"; shift 2;;
    --constraints) CONSTRAINTS="$2"; shift 2;;
    --json) RAW="$2"; shift 2;;
    -h|--help)
      echo "Usage: aid_ask.sh --goal G --context C --tried T --question Q [--error E] [--constraints K]"
      exit 0;;
    *) echo "[aid-network] unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -n "$RAW" ]]; then
  # Auto-fill client_id and model from config if caller's JSON didn't include them.
  BODY="$(echo "$RAW" | jq --arg cid "$AI_AID_CLIENT_ID" --arg model "$AI_AID_MODEL" \
    '. as $b | $b
       | .client_id = ($b.client_id // $cid)
       | .model     = ($b.model     // $model)')"
else
  BODY="$(jq -n \
    --arg cid "$AI_AID_CLIENT_ID" --arg model "$AI_AID_MODEL" \
    --arg goal "$GOAL" --arg ctx "$CONTEXT" --arg tried "$TRIED" \
    --arg err "$ERROR" --arg cons "$CONSTRAINTS" --arg q "$QUESTION" \
    '{client_id:$cid, model:$model, goal:$goal, context:$ctx, tried:$tried, question:$q}
     + (if $err != "" then {error:$err} else {} end)
     + (if $cons != "" then {constraints:$cons} else {} end)')"
fi

_aid_curl POST "${AI_AID_SERVER_URL%/}/api/requests" "$BODY"
