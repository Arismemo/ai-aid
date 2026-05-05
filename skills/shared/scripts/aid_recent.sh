#!/usr/bin/env bash
# Show the global activity feed (newest first) — what the network is doing.
#
# Usage: aid_recent.sh [LIMIT]
#   LIMIT defaults to 30, max 200.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"
_aid_load_config

LIMIT="${1:-30}"
_aid_curl GET "${AI_AID_SERVER_URL%/}/api/recent?limit=${LIMIT}"
