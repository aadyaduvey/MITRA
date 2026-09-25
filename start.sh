#!/usr/bin/env bash
# One-command start for MITRA on macOS / Linux (Windows: use start.cmd).
#   ./start.sh            start API + dashboard (+ bot if TELEGRAM_TOKEN is set); Ctrl+C stops all
#   ./start.sh --reseed   fresh demo data
#   ./start.sh --smoke    start, check every part, print PASS/FAIL, stop
# Ports: API_PORT (default 8000), WEB_PORT (default 5173).
set -uo pipefail

API_PORT=${API_PORT:-8000}
WEB_PORT=${WEB_PORT:-5173}
RESEED=0; SMOKE=0
for arg in "$@"; do
  case $arg in
    --reseed) RESEED=1 ;;
    --smoke) SMOKE=1 ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

ROOT=$(cd "$(dirname "$0")" && pwd)
LOGS="$ROOT/logs"; mkdir -p "$LOGS"
PIDS=()

fail() { echo "ERROR: $*" >&2; exit 1; }
cleanup() { echo "Stopping MITRA..."; for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null; done; }
trap cleanup EXIT
trap 'exit 130' INT TERM

wait_http() {  # url seconds
  for _ in $(seq 1 $(($2 * 2))); do curl -fs -o /dev/null "$1" && return 0; sleep 0.5; done; return 1
}

command -v uv >/dev/null || fail "uv not found: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v pnpm >/dev/null || fail "pnpm not found: install Node 18+, then npm install -g pnpm"
for port in "$API_PORT" "$WEB_PORT"; do
  curl -s -o /dev/null --max-time 2 "http://localhost:$port/" && fail "port $port already in use (is MITRA running?)"
done

echo "[1/4] Backend packages..."
(cd "$ROOT/backend" && uv sync --quiet) || fail "uv sync failed"
if [ $RESEED = 1 ] || [ ! -f "$ROOT/backend/data/mitra.db" ]; then
  (cd "$ROOT/backend" && uv run python -m app.seed) || fail "seeding failed"
fi
echo "[2/4] Dashboard packages..."
[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && pnpm install --silent) || fail "pnpm install failed"

export MITRA_API_URL="http://127.0.0.1:$API_PORT"
echo "[3/4] API on :$API_PORT, dashboard on :$WEB_PORT..."
(cd "$ROOT/backend" && exec uv run uvicorn app.main:app --port "$API_PORT") >"$LOGS/api.log" 2>&1 & PIDS+=($!)
wait_http "http://127.0.0.1:$API_PORT/health" 60 || fail "API did not start (see logs/api.log)"
(cd "$ROOT/frontend" && exec pnpm dev --port "$WEB_PORT" --strictPort) >"$LOGS/dashboard.log" 2>&1 & PIDS+=($!)
wait_http "http://localhost:$WEB_PORT/" 60 || fail "dashboard did not start (see logs/dashboard.log)"

if [ $SMOKE = 1 ]; then
  status=0
  for path in /health /api/collectors /api/ministry/summary /api/flow/sankey /api/passport/1 \
              "/api/epr/report?format=pdf" /api/classify/status /; do
    if curl -fs -o /dev/null "http://localhost:$WEB_PORT$path"; then echo "  PASS  $path"; else echo "  FAIL  $path"; status=1; fi
  done
  [ $status = 0 ] && echo "SMOKE TEST PASSED" || echo "SMOKE TEST FAILED"
  exit $status
fi

BOT="skipped: no TELEGRAM_TOKEN (offline demo: cd backend && uv run python -m app.bot.offline_demo)"
if [ -n "${TELEGRAM_TOKEN:-}" ] || grep -qs '^ *TELEGRAM_TOKEN *= *[^ ]' "$ROOT/backend/.env"; then
  echo "[4/4] Telegram bot..."
  (cd "$ROOT/backend" && exec uv run python -m app.bot.telegram_bot) >"$LOGS/bot.log" 2>&1 & PIDS+=($!)
  BOT="running (logs/bot.log)"
fi

cat <<EOF

MITRA is running
  Dashboard   http://localhost:$WEB_PORT
  API docs    http://localhost:$API_PORT/docs
  Telegram    $BOT
  Logs        $LOGS
Press Ctrl+C to stop everything.
EOF
wait -n "${PIDS[@]}"
echo "A part stopped unexpectedly; see $LOGS" >&2
exit 1
