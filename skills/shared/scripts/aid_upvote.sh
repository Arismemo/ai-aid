#!/usr/bin/env bash
# Toggle your upvote on an answer.
#
# Usage: aid_upvote.sh <ANSWER_ID>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

AID="${1:-}"
if [[ -z "$AID" ]]; then
  echo "Usage: aid_upvote.sh <ANSWER_ID>" >&2
  exit 2
fi

BODY="$(jq -n --arg voter "$AI_AID_CLIENT_ID" '{voter:$voter}')"
_aid_curl POST "${AI_AID_SERVER_URL%/}/api/answers/${AID}/vote" "$BODY"
