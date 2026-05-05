#!/usr/bin/env bash
# Shared helpers for ai-aid skill scripts.
# Sourced (not executed) by every aid_*.sh script.

set -euo pipefail

# Config discovery: env override wins, else config.json next to scripts dir parent.
_aid_script_dir() {
  cd "$(dirname "${BASH_SOURCE[1]}")" >/dev/null 2>&1 && pwd
}

_aid_load_config() {
  local cfg="${AI_AID_CONFIG:-}"
  if [[ -z "$cfg" ]]; then
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    # Default: config.json one directory up from the scripts dir
    cfg="${script_dir}/../config.json"
  fi
  if [[ ! -f "$cfg" ]]; then
    echo "[aid-network] config not found at: $cfg" >&2
    echo "[aid-network] Set AI_AID_CONFIG=/path/to/config.json or place config.json in the skill root." >&2
    return 2
  fi
  if ! command -v jq >/dev/null 2>&1; then
    echo "[aid-network] jq is required but not installed (brew install jq)" >&2
    return 2
  fi
  AI_AID_SERVER_URL="$(jq -r '.server_url' "$cfg")"
  AI_AID_CLIENT_ID="$(jq -r '.client_id' "$cfg")"
  AI_AID_MODEL="$(jq -r '.model' "$cfg")"
  if [[ -z "$AI_AID_SERVER_URL" || "$AI_AID_SERVER_URL" == "null" ]]; then
    echo "[aid-network] config missing server_url" >&2
    return 2
  fi
  if [[ -z "$AI_AID_CLIENT_ID" || "$AI_AID_CLIENT_ID" == "null" ]]; then
    echo "[aid-network] config missing client_id" >&2
    return 2
  fi
  if [[ -z "$AI_AID_MODEL" || "$AI_AID_MODEL" == "null" ]]; then
    echo "[aid-network] config missing model" >&2
    return 2
  fi
}

_aid_curl() {
  # Wrap curl with consistent options + readable error on network failure.
  local method="$1"; shift
  local url="$1"; shift
  local body="${1:-}"
  local out http_code
  out="$(mktemp)"
  if [[ -z "$body" ]]; then
    http_code="$(curl -s -o "$out" -w "%{http_code}" -X "$method" "$url" || echo 000)"
  else
    http_code="$(curl -s -o "$out" -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" -d "$body" "$url" || echo 000)"
  fi
  if [[ "$http_code" == "000" ]]; then
    echo "[aid-network] server unreachable: $url" >&2
    rm -f "$out"
    return 1
  fi
  cat "$out"
  rm -f "$out"
  if [[ "$http_code" =~ ^2 ]]; then
    return 0
  fi
  return 1
}
