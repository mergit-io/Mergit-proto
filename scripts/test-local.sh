#!/usr/bin/env bash
set -euo pipefail

# Local checks: install, syntax, backend test suite, frontend build.
#
# The test suite used to be missing from this script — it ran py_compile and a frontend
# build, printed "Local checks passed", and never executed a single test. Anyone
# following the README could break the backend and still see a green run.
#
# Optional: point the live-deployment suite at a running instance.
#   MERGIT_BASE_URL=https://mergit.onrender.com ./scripts/test-local.sh
#   MERGIT_LIVE_GOAL=1 MERGIT_BASE_URL=... ./scripts/test-local.sh   # also submits a real goal

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  python -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m py_compile ./*.py ./api/*.py ./tools/*.py
.venv/bin/python -m pytest -q

cd "$ROOT/frontend"
npm install
npm run build

echo "Local checks passed."
