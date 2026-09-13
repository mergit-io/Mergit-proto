#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install
fi
npm run build

cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  python -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt

exec .venv/bin/python -m uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
