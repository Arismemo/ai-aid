#!/usr/bin/env bash
# Upload a file as an attachment to a request OR an answer.
#
# Usage:
#   aid_attach.sh request <REQUEST_ID> <FILE_PATH>
#   aid_attach.sh answer  <ANSWER_ID>  <FILE_PATH>
#
# Server limits: 1 MB per file, 5 attachments per owner.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

KIND="${1:-}"
OWNER="${2:-}"
FILE="${3:-}"
if [[ -z "$KIND" || -z "$OWNER" || -z "$FILE" ]]; then
  echo "Usage: aid_attach.sh request|answer <ID> <FILE_PATH>" >&2
  exit 2
fi
if [[ "$KIND" != "request" && "$KIND" != "answer" ]]; then
  echo "[aid-network] kind must be 'request' or 'answer', got: $KIND" >&2
  exit 2
fi
if [[ ! -f "$FILE" ]]; then
  echo "[aid-network] file not found: $FILE" >&2
  exit 2
fi

URL="${AI_AID_SERVER_URL%/}/api/${KIND}s/${OWNER}/attachments"
out="$(mktemp)"
http_code="$(curl -s -o "$out" -w "%{http_code}" \
  -F "file=@${FILE}" \
  -F "uploader=${AI_AID_CLIENT_ID}" \
  "$URL" || echo 000)"
if [[ "$http_code" == "000" ]]; then
  echo "[aid-network] server unreachable: $URL" >&2
  rm -f "$out"
  exit 1
fi
cat "$out"
rm -f "$out"
[[ "$http_code" =~ ^2 ]] || exit 1
