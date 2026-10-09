#!/usr/bin/env bash
# Run the E2E suite against a local backend (no Docker): fresh temp DB, mock LLM,
# simulator, built frontend from frontend/out, on port 8020 (override with PORT).
# Usage: test/run-local.sh [extra playwright args]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8020}"
UV="${UV:-uv}"
command -v "$UV" >/dev/null 2>&1 || UV="/c/Users/mauro/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe/uv.exe"

[ -f "$ROOT/frontend/out/index.html" ] || { echo "frontend/out missing: run 'npm run build' in frontend/"; exit 1; }

# A previous backend still shutting down would answer the health check with a stale DB.
for _ in $(seq 1 15); do
  curl -fsS -m 1 "http://localhost:$PORT/api/health" >/dev/null 2>&1 || break
  sleep 1
done
if curl -fsS -m 1 "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
  echo "port $PORT is already serving; stop it first"; exit 1
fi

TMP="$(mktemp -d)"
LOG="$TMP/backend.log"
cleanup() {
  [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true
  # On Windows (Git Bash) killing the subshell leaves uvicorn running; stop whatever listens on PORT.
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force }" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

(
  cd "$ROOT/backend"
  env -u MASSIVE_API_KEY -u OPENROUTER_API_KEY \
    LLM_MOCK=true MASSIVE_API_KEY= OPENROUTER_API_KEY= \
    DB_PATH="$TMP/finally.db" STATIC_DIR="$ROOT/frontend/out" \
    "$UV" run uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
) >"$LOG" 2>&1 &
PID=$!

for _ in $(seq 1 60); do
  curl -fsS "http://localhost:$PORT/api/health" >/dev/null 2>&1 && break
  kill -0 "$PID" 2>/dev/null || { cat "$LOG"; exit 1; }
  sleep 1
done
echo "backend up on :$PORT (log: $LOG)"

cd "$ROOT/test"
BASE_URL="http://localhost:$PORT" npx playwright test "$@"
