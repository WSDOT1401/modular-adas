#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$APP_DIR/build"
VSS_SCRIPT="$APP_DIR/pi/vss_reader.py"

if [[ ! -x "$BUILD_DIR/w124_cluster" ]]; then
  echo "Binary not found at $BUILD_DIR/w124_cluster" >&2
  echo "Build first: cmake -S . -B build && cmake --build build -j" >&2
  exit 1
fi

# Start VSS reader in the background (reads gearbox sender → state.json)
# Set VSS_DISABLE=1 to skip (e.g. for bench testing with mock_state_writer.py)
VSS_PID=""
if [[ "${VSS_DISABLE:-0}" != "1" && -f "$VSS_SCRIPT" ]]; then
  python3 "$VSS_SCRIPT" &
  VSS_PID=$!
  echo "VSS reader started (PID $VSS_PID)"
fi

# Start CarPlay sidecar server in the background
# Set CARPLAY_DISABLE=1 to skip (e.g. if dongle is not yet installed)
CARPLAY_PID=""
CARPLAY_DIR="$APP_DIR/carplay"
if [[ "${CARPLAY_DISABLE:-0}" != "1" && -f "$CARPLAY_DIR/server.js" ]]; then
  if ! command -v node &>/dev/null; then
    echo "WARNING: node not found, CarPlay sidecar will not start." >&2
  else
    # Install npm deps on first run if node_modules is missing
    if [[ ! -d "$CARPLAY_DIR/node_modules" ]]; then
      echo "Installing CarPlay npm dependencies..."
      (cd "$CARPLAY_DIR" && npm install --omit=dev)
    fi

    node "$CARPLAY_DIR/server.js" &
    CARPLAY_PID=$!
    echo "CarPlay server started (PID $CARPLAY_PID)"
  fi
fi

# Cleanup all background processes when this script exits
cleanup() {
  [[ -n "$VSS_PID"     ]] && kill "$VSS_PID"     2>/dev/null || true
  [[ -n "$CARPLAY_PID" ]] && kill "$CARPLAY_PID" 2>/dev/null || true
}
trap cleanup EXIT

exec "$BUILD_DIR/w124_cluster" --state --state-file="$APP_DIR/state.json" --poll-ms=120
