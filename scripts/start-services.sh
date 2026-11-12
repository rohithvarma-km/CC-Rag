#!/usr/bin/env bash
# Start backend (FastAPI :8000) and frontend (Vite :5173) in the background.
# Usage: scripts/start-services.sh [stop]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$ROOT/.logs"; mkdir -p "$LOGS"

stop() {
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "$ROOT/frontend/node_modules/.bin/vite" 2>/dev/null || true
  sleep 1
}

if [[ "${1:-}" == "stop" ]]; then stop; echo "stopped"; exit 0; fi

[[ -f "$ROOT/backend/.env" ]] || { echo "Missing backend/.env (copy backend/.env.example)"; exit 1; }
[[ -f "$ROOT/frontend/.env" ]] || { echo "Missing frontend/.env (copy frontend/.env.example)"; exit 1; }
[[ -x "$ROOT/backend/venv/bin/uvicorn" ]] || { echo "Run: cd backend && python3 -m venv venv && venv/bin/pip install -r requirements.txt"; exit 1; }
[[ -d "$ROOT/frontend/node_modules" ]] || (cd "$ROOT/frontend" && npm install)

stop
(cd "$ROOT/backend" && nohup ./venv/bin/uvicorn app.main:app --port 8000 > "$LOGS/backend.log" 2>&1 &)
(cd "$ROOT/frontend" && nohup npm run dev -- --port 5173 --strictPort > "$LOGS/frontend.log" 2>&1 &)

for i in $(seq 1 30); do
  be=$(curl -s -o /dev/null -w "%{http_code}" localhost:8000/health || true)
  fe=$(curl -s -o /dev/null -w "%{http_code}" localhost:5173 || true)
  [[ "$be" == "200" && "$fe" == "200" ]] && { echo "Backend http://localhost:8000  Frontend http://localhost:5173  (logs: .logs/)"; exit 0; }
  sleep 1
done
echo "Services failed to start; see $LOGS"; exit 1
