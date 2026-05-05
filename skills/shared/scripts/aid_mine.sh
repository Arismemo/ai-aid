#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

URL="${AI_AID_SERVER_URL%/}/api/requests?status=all&client_id=${AI_AID_CLIENT_ID}&mine=1"
_aid_curl GET "$URL"
