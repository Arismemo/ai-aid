#!/usr/bin/env bash
# Close one of your own open requests.
# Usage: aid_close.sh <RID>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

RID="${1:-}"
if [[ -z "$RID" ]]; then
  echo "Usage: aid_close.sh <RID>" >&2
  exit 2
fi
_aid_curl POST "${AI_AID_SERVER_URL%/}/api/requests/${RID}/close"
