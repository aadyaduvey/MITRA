#!/usr/bin/env bash
# One-command start for MITRA on macOS / Linux (Windows: use start.cmd).
#   ./start.sh            start API + dashboard (+ bot if TELEGRAM_TOKEN is set); Ctrl+C stops all
#   ./start.sh --reseed   fresh demo data
#   ./start.sh --smoke    start, check every part, print PASS/FAIL, stop
#   ./start.sh --share    also make a public link (Cloudflare tunnel) that opens on any device, any network;
#                         other devices can view and download reports but cannot change data
# Ports: API_PORT (default 8000), WEB_PORT (default 5173).
set -uo pipefail

API_PORT=${API_PORT:-8000}
WEB_PORT=${WEB_PORT:-5173}
RESEED=0; SMOKE=0; SHARE=0
for arg in "$@"; do
  case $arg in
    --reseed) RESEED=1 ;;
    --smoke) SMOKE=1 ;;
    --share) SHARE=1 ;;
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

cloudflared_bin() {  # prints the path, downloading a copy into tools/ on first use
  if command -v cloudflared >/dev/null; then command -v cloudflared; return 0; fi
  local url out
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) out="$ROOT/tools/cloudflared.exe"
      url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" ;;
    Linux) out="$ROOT/tools/cloudflared"
      url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" ;;
    *) echo "install cloudflared first (macOS: brew install cloudflared)" >&2; return 1 ;;
  esac
  if [ ! -x "$out" ]; then
    echo "      Downloading Cloudflare tunnel (one time, about 60 MB)..." >&2
    mkdir -p "$ROOT/tools" && curl -fsSL -o "$out" "$url" && chmod +x "$out" || return 1
  fi
  echo "$out"
}

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

SHARE_LINE=""
if [ $SHARE = 1 ]; then
  echo "      Making a public link..."
  CF=$(cloudflared_bin) || fail "could not get cloudflared"
  "$CF" tunnel --url "http://localhost:$WEB_PORT" --no-autoupdate >"$LOGS/tunnel.log" 2>&1 & PIDS+=($!)
  LINK=""
  for _ in $(seq 1 60); do
    LINK=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOGS/tunnel.log" | head -1)
    [ -n "$LINK" ] && break; sleep 1
  done
  [ -n "$LINK" ] || fail "no public link after 60 s (see logs/tunnel.log)"
  SHARE_LINE="  Share link  $LINK   (any device, any network; view-only)"
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
$SHARE_LINE
  API docs    http://localhost:$API_PORT/docs
  Telegram    $BOT
  Logs        $LOGS
Press Ctrl+C to stop everything.
EOF
wait -n "${PIDS[@]}"
echo "A part stopped unexpectedly; see $LOGS" >&2
exit 1
