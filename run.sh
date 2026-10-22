#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$ROOT/lucas_ui"
BACKEND_PORT=8765
FRONTEND_PORT=5173

# Colors
GRN='\033[0;32m'; BLU='\033[0;34m'; CYN='\033[0;36m'; RED='\033[0;31m'; YLW='\033[1;33m'; NC='\033[0m'

cleanup() {
  echo ""
  echo -e "${RED}⏹  Shutting down...${NC}"
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  # Clear any stale processes on our ports
  fuser -k "${BACKEND_PORT}/tcp" 2>/dev/null || true
  fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null || true
  echo -e "${GRN}✓ Both processes stopped${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── Free ports first (kill any stale processes) ──
fuser -k "${BACKEND_PORT}/tcp" 2>/dev/null && echo -e "${YLW}⚠  Killed stale process on port ${BACKEND_PORT}${NC}" || true
fuser -k "${FRONTEND_PORT}/tcp" 2>/dev/null && echo -e "${YLW}⚠  Killed stale Vite on port ${FRONTEND_PORT}${NC}" || true
sleep 0.3

# ── Kill stale Lucas instances and clean the pid file ──
if [ -f "$HOME/.lucas/lucas.pid" ]; then
  STALE_PID="$(cat "$HOME/.lucas/lucas.pid" 2>/dev/null || true)"
  if [ -n "$STALE_PID" ] && kill -0 "$STALE_PID" 2>/dev/null; then
    echo -e "${YLW}⚠  Killing stale Lucas instance (PID $STALE_PID)${NC}"
    kill "$STALE_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$STALE_PID" 2>/dev/null || true
  fi
  rm -f "$HOME/.lucas/lucas.pid"
fi
pkill -f "main.py" 2>/dev/null && echo -e "${YLW}⚠  Killed stray main.py instance${NC}" || true
pkill -f "telegram_bot" 2>/dev/null && echo -e "${YLW}⚠  Killed stray telegram bot${NC}" || true

# ── Start backend ──
echo -e "${BLU}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLU}║  🟢 Starting Lucas backend (Python)...    ║${NC}"
echo -e "${BLU}╚══════════════════════════════════════════╝${NC}"
cd "$ROOT"
python main.py --ui-mode=web &
BACKEND_PID=$!

# Wait for backend — check PID is alive (no nc -z; that triggers InvalidMessage on ws://)
echo -e "${CYN}⏳ Waiting for backend on port $BACKEND_PORT...${NC}"
BACKEND_OK=false
for i in $(seq 1 30); do
  if kill -0 $BACKEND_PID 2>/dev/null; then
    BACKEND_OK=true
    echo -e "${GRN}✓ Backend ready on ws://localhost:$BACKEND_PORT${NC}"
    break
  fi
  sleep 0.5
done

if [ "$BACKEND_OK" = false ]; then
  echo -e "${RED}✗ Backend did not start within 15s. Check error output.${NC}"
  kill $BACKEND_PID 2>/dev/null || true
  exit 1
fi

# Small extra wait for the WebSocket server to be listening
sleep 1

# ── Start frontend ──
echo ""
echo -e "${BLU}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLU}║  🟢 Starting Lucas frontend (Vite)...     ║${NC}"
echo -e "${BLU}╚══════════════════════════════════════════╝${NC}"
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# Wait a moment for Vite to start
sleep 2
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
  echo -e "${RED}✗ Frontend exited prematurely${NC}"
  exit 1
fi

echo ""
echo -e "${GRN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GRN}║  ✅ Both services are running             ║${NC}"
echo -e "${GRN}║                                          ║${NC}"
echo -e "${GRN}║  Frontend → http://localhost:${FRONTEND_PORT}         ${NC}"
echo -e "${GRN}║  Backend  → ws://localhost:${BACKEND_PORT}           ${NC}"
echo -e "${GRN}║                                          ║${NC}"
echo -e "${GRN}║  Press Ctrl+C to stop both                ║${NC}"
echo -e "${GRN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Wait for either process to exit, then clean up
set +e
while true; do
  if ! kill -0 $BACKEND_PID 2>/dev/null || ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}⚠  A process exited unexpectedly${NC}"
    break
  fi
  sleep 1
done
cleanup
