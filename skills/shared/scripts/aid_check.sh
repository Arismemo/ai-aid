#!/usr/bin/env bash
# Show a single request with all answers.
# Usage: aid_check.sh <RID>
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

RID="${1:-}"
if [[ -z "$RID" ]]; then
  echo "Usage: aid_check.sh <RID>" >&2
  exit 2
fi
_aid_curl GET "${AI_AID_SERVER_URL%/}/api/requests/${RID}"
