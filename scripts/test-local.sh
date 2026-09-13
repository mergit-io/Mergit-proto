#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  python -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m py_compile ./*.py ./api/*.py ./tools/*.py

cd "$ROOT/frontend"
npm install
npm run build

echo "Local checks passed."
