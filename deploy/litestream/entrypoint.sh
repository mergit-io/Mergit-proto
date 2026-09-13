#!/bin/sh
# Mergit container entrypoint.
#
# Two modes, decided by whether replication is configured:
#
#   LITESTREAM_BUCKET set    -> restore the DB from object storage, then run uvicorn as
#                               a CHILD of litestream so that (a) writes stream out
#                               continuously and (b) SIGTERM triggers a final sync.
#   LITESTREAM_BUCKET unset  -> run uvicorn directly. This is what `make dev` and every
#                               test run gets, so the image is identical everywhere and a
#                               missing bucket is never a boot failure.
#
# SIGNALS — this is the part that actually protects the data.
# Render sends SIGTERM on redeploy and waits 30s before SIGKILL. `litestream replicate
# -exec` catches SIGTERM, forwards it to the child, waits for the child to exit, then
# calls Close(), which flushes the final LTX file. So a redeploy has an RPO of 0.
# `exec` below makes litestream PID 1; run-app.sh's own `exec` makes uvicorn replace its
# shell. Without BOTH, a shell swallows the signal and the final sync never happens.

set -eu

APP=/usr/local/bin/run-app.sh

if [ -z "${LITESTREAM_BUCKET:-}" ]; then
  echo "litestream: LITESTREAM_BUCKET unset — running without replication (ephemeral DB)"
  exec "${APP}"
fi

DB_PATH="${DB_PATH:-/data/mergit.db}"
mkdir -p "$(dirname "${DB_PATH}")"

# Restore on boot.
#   -if-replica-exists  exit 0 (not 1) when the bucket is empty. That is the first-ever
#                       boot; main.py's init_db then creates the schema from scratch.
#   -if-db-not-exists   refuse to clobber a database already on disk. Irrelevant on
#                       Render free (the filesystem is always empty at boot) but it is
#                       what makes this same script safe on a box with a real disk.
echo "litestream: restoring ${DB_PATH} from s3://${LITESTREAM_BUCKET}/mergit"
litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml "${DB_PATH}"

if [ -f "${DB_PATH}" ]; then
  echo "litestream: database present, $(wc -c < "${DB_PATH}") bytes"
else
  echo "litestream: no replica found — starting from an empty database"
fi

exec litestream replicate -config /etc/litestream.yml -exec "${APP}"
