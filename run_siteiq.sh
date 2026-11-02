#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --quiet -r requirements.txt
if [ ! -f frontend/dist/index.html ]; then
  command -v npm >/dev/null || { echo "Node.js 20 or newer is needed to build the interface: https://nodejs.org" >&2; exit 1; }
  (cd frontend && npm ci --no-audit --no-fund && npx vite build)
fi
PORT="${SITEIQ_PORT:-8765}"
echo "SiteIQ is running at http://127.0.0.1:${PORT}"
( sleep 2; command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 || command -v open >/dev/null && open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 || true ) &
exec python -m uvicorn siteiq.api:app --host 127.0.0.1 --port "${PORT}"
