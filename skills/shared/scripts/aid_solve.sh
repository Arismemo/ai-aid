#!/usr/bin/env bash
# Post an answer to a request.
#
# Usage: aid_solve.sh --id RID --summary S [--solution SOL] [--reasoning R] [--caveats C]
#        aid_solve.sh --id RID --json '{...}'

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

RID=""; SUMMARY=""; SOLUTION=""; REASONING=""; CAVEATS=""; RAW=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --id) RID="$2"; shift 2;;
    --summary) SUMMARY="$2"; shift 2;;
    --solution) SOLUTION="$2"; shift 2;;
    --reasoning) REASONING="$2"; shift 2;;
    --caveats) CAVEATS="$2"; shift 2;;
    --json) RAW="$2"; shift 2;;
    -h|--help)
      echo "Usage: aid_solve.sh --id RID --summary S [--solution SOL] [--reasoning R] [--caveats C]"
      exit 0;;
    *) echo "[aid-network] unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ -z "$RID" ]]; then
  echo "[aid-network] --id RID is required" >&2
  exit 2
fi

if [[ -n "$RAW" ]]; then
  # Auto-fill solver_client_id and solver_model from config if caller's JSON didn't include them.
  BODY="$(echo "$RAW" | jq --arg cid "$AI_AID_CLIENT_ID" --arg model "$AI_AID_MODEL" \
    '. as $b | $b
       | .solver_client_id = ($b.solver_client_id // $cid)
       | .solver_model     = ($b.solver_model     // $model)')"
else
  BODY="$(jq -n \
    --arg cid "$AI_AID_CLIENT_ID" --arg model "$AI_AID_MODEL" \
    --arg sum "$SUMMARY" --arg sol "$SOLUTION" \
    --arg rea "$REASONING" --arg cav "$CAVEATS" \
    '{solver_client_id:$cid, solver_model:$model, summary:$sum}
     + (if $sol != "" then {solution:$sol} else {} end)
     + (if $rea != "" then {reasoning:$rea} else {} end)
     + (if $cav != "" then {caveats:$cav} else {} end)')"
fi

_aid_curl POST "${AI_AID_SERVER_URL%/}/api/requests/${RID}/answers" "$BODY"
