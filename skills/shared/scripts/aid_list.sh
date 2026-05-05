#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

# Default: open only, exclude self
URL="${AI_AID_SERVER_URL%/}/api/requests?status=open&exclude_client=${AI_AID_CLIENT_ID}"
_aid_curl GET "$URL"
