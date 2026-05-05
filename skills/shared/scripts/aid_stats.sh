#!/usr/bin/env bash
# Show your own ai-aid stats: asks/answers/accept-rate.
#
# Usage: aid_stats.sh [CLIENT_ID]
#   CLIENT_ID defaults to the configured client_id (yourself).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

WHO="${1:-$AI_AID_CLIENT_ID}"
# URL-encode minimally
WHO_ENC="$(printf %s "$WHO" | jq -sRr @uri)"
_aid_curl GET "${AI_AID_SERVER_URL%/}/api/stats?client_id=${WHO_ENC}"
