#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_PATH="/tmp/mergit-${STAMP}.db"

mkdir -p "$BACKUP_DIR"

docker compose --env-file "$ENV_FILE" exec -T mergit python - "$BACKUP_PATH" <<'PY'
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

docker compose --env-file "$ENV_FILE" cp "mergit:${BACKUP_PATH}" "$BACKUP_DIR/mergit-${STAMP}.db"
docker compose --env-file "$ENV_FILE" exec -T mergit rm -f "$BACKUP_PATH"

echo "$BACKUP_DIR/mergit-${STAMP}.db"
