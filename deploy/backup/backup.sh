#!/usr/bin/env bash
# ai-aid SQLite backup. Uses `sqlite3 .backup` to get a consistent snapshot
# even while the server is writing.
#
# Usage: backup.sh [DATA_DIR] [KEEP_DAYS]
#   DATA_DIR defaults to ./data
#   KEEP_DAYS defaults to 7

set -euo pipefail

DATA_DIR="${1:-./data}"
KEEP_DAYS="${2:-7}"

DB="${DATA_DIR}/ai-aid.db"
OUT_DIR="${DATA_DIR}/backups"

if [[ ! -f "$DB" ]]; then
  echo "[backup] no db at $DB, aborting" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
TS="$(date +%F_%H%M%S)"
TARGET="${OUT_DIR}/ai-aid-${TS}.db"

# Use python3 if sqlite3 CLI is missing (more universal on minimal hosts).
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '${TARGET}'"
else
  python3 - "$DB" "$TARGET" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
PY
fi
gzip -9 "$TARGET"
echo "[backup] wrote ${TARGET}.gz"

# Prune old
find "$OUT_DIR" -type f -name 'ai-aid-*.db.gz' -mtime "+${KEEP_DAYS}" -delete
