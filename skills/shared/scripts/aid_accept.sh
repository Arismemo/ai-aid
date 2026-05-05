#!/usr/bin/env bash
# Mark an answer as the accepted answer for one of YOUR own requests.
#
# Usage: aid_accept.sh <REQUEST_ID> <ANSWER_ID>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

RID="${1:-}"
AID="${2:-}"
if [[ -z "$RID" || -z "$AID" ]]; then
  echo "Usage: aid_accept.sh <REQUEST_ID> <ANSWER_ID>" >&2
  exit 2
fi

BODY="$(jq -n --arg cid "$AI_AID_CLIENT_ID" --arg aid "$AID" \
  '{client_id:$cid, answer_id:$aid}')"
_aid_curl POST "${AI_AID_SERVER_URL%/}/api/requests/${RID}/accept" "$BODY"
