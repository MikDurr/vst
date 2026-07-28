#!/usr/bin/env bash
# Launch vocalign: the Python engine (:8010) and the UI (:5180).
# Ports deliberately avoid the vocal training studio's 8000/5173 so both
# projects can run at once. Ctrl+C stops both.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

API_PORT=8010
WEB_PORT=5180   # must match vite.config.ts and api/main.py's CORS allowlist

set -m   # each job in its own process group, so cleanup kills children too
API_PID=""; WEB_PID=""

# Both servers get their stdin from /dev/null, and that is load-bearing.
#
# `set -m` above puts each server in its own process group, which is what lets
# cleanup kill a whole tree — but it also means neither is in the terminal's
# *foreground* process group. Vite binds stdin in raw mode to offer its
# keyboard shortcuts when it sees a TTY; a background process group reading the
# controlling terminal is sent SIGTTIN, and the default action for SIGTTIN is
# to suspend the process. Vite would come up, get stopped mid-startup, and
# :5180 would then accept connections but never answer one — a browser tab
# spinning forever with a perfectly healthy engine behind it.
#
# Redirecting stdin means Vite doesn't see a TTY, doesn't bind shortcuts, and
# never reads the terminal. The cost is that its interactive shortcuts are
# gone, which is no loss for a server started by a launcher script.
NO_STDIN=/dev/null

kill_tree() {
  local pid="$1"; [ -z "$pid" ] && return 0
  local pgid; pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
  if [ -n "$pgid" ]; then
    kill -TERM -"$pgid" 2>/dev/null || true; sleep 1; kill -KILL -"$pgid" 2>/dev/null || true
  else kill -TERM "$pid" 2>/dev/null || true; fi
}
cleanup() { trap - EXIT INT TERM; echo; echo "Stopping…"; kill_tree "$WEB_PID"; kill_tree "$API_PID"; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

port_busy() { lsof -ti tcp:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

if port_busy $API_PORT; then echo "✓ engine already on :$API_PORT"
else
  echo "→ starting engine on :$API_PORT"
  "$DIR/.venv/bin/python" -m uvicorn api.main:app --port "$API_PORT" < "$NO_STDIN" & API_PID=$!
fi
for i in $(seq 1 60); do
  curl -fsS -m 1 "http://localhost:$API_PORT/api/health" >/dev/null 2>&1 && { echo "✓ engine ready"; break; }
  [ "$i" -eq 60 ] && { echo "✗ engine failed to start" >&2; exit 1; }
  sleep 1
done

if port_busy $WEB_PORT; then echo "✓ UI already on :$WEB_PORT"
else
  echo "→ starting UI on :$WEB_PORT"
  ( cd "$DIR/web" && npm run dev < "$NO_STDIN" ) & WEB_PID=$!
fi
for i in $(seq 1 60); do
  curl -fsS -m 1 -o /dev/null "http://localhost:$WEB_PORT/" 2>/dev/null && break
  [ "$i" -eq 60 ] && { echo "✗ UI failed to start" >&2; exit 1; }
  sleep 1
done

# Open the browser once both servers answer. Set NO_OPEN=1 to suppress it —
# useful when the tab is already open, since `open` would refocus it.
[ -n "${NO_OPEN:-}" ] || open "http://localhost:$WEB_PORT" 2>/dev/null || true

echo
echo "  vocalign → http://localhost:$WEB_PORT"
echo "  Ctrl+C to stop."
echo
wait
