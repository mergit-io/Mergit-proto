#!/bin/sh
# The application itself. Kept in its own file so that nothing — not the entrypoint,
# not litestream's -exec shell-word splitting — ever has to re-quote this command.
# `exec` is required: it makes uvicorn replace this shell, so the SIGTERM litestream
# forwards lands on uvicorn instead of on a shell that ignores it.
exec python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips '*'
