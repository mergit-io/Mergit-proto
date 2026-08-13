#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_PATH="/tmp/mergit-${STAMP}.db"

mkdir -p "$BACKUP_DIR"

# Whichever engine runs the stack. Override with COMPOSE="podman-compose" if the
# autodetect picks the wrong one.
if [ -z "${COMPOSE:-}" ]; then
  if command -v docker >/dev/null 2>&1; then
    COMPOSE="docker compose"
  elif command -v podman-compose >/dev/null 2>&1; then
    COMPOSE="podman-compose"
  elif command -v podman >/dev/null 2>&1; then
    COMPOSE="podman compose"
  else
    echo "no container engine found — set COMPOSE=..." >&2
    exit 1
  fi
fi

$COMPOSE --env-file "$ENV_FILE" exec -T mergit python - "$BACKUP_PATH" <<'PY'
import sqlite3
import sys
from config import settings

source = sqlite3.connect(settings.db_path)
target = sqlite3.connect(sys.argv[1])
with target:
    source.backup(target)
target.close()
source.close()
PY

$COMPOSE --env-file "$ENV_FILE" cp "mergit:${BACKUP_PATH}" "$BACKUP_DIR/mergit-${STAMP}.db"
$COMPOSE --env-file "$ENV_FILE" exec -T mergit rm -f "$BACKUP_PATH"

echo "$BACKUP_DIR/mergit-${STAMP}.db"
