#!/usr/bin/env bash
set -euo pipefail

# This script lives in deploy/ — the repo root is one level up.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The cluster app still lives in qt_cluster/ (moves to apps/cluster/ in a later phase).
CLUSTER_DIR="$REPO_ROOT/qt_cluster"
BUILD_DIR="$CLUSTER_DIR/build"

# Shared runtime dir — where the cluster reads/writes state.json,
# carplay_status.json and trip_reset.flag. Every producer must agree on this,
# so we export it for the VSS reader and the CarPlay sidecar.
export W124_RUNTIME_DIR="${W124_RUNTIME_DIR:-$CLUSTER_DIR}"
export CARPLAY_STATUS_FILE="$W124_RUNTIME_DIR/carplay_status.json"

VSS_SCRIPT="$REPO_ROOT/services/vss/vss_reader.py"
CARPLAY_DIR="$REPO_ROOT/services/carplay"

if [[ ! -x "$BUILD_DIR/w124_cluster" ]]; then
  echo "Binary not found at $BUILD_DIR/w124_cluster" >&2
  echo "Build first: cmake -S qt_cluster -B qt_cluster/build && cmake --build qt_cluster/build -j" >&2
  exit 1
fi

# Start VSS reader in the background (reads gearbox sender → UDP 9100).
# Set VSS_DISABLE=1 to skip (e.g. for bench testing with mock_state_writer.py).
VSS_PID=""
if [[ "${VSS_DISABLE:-0}" != "1" && -f "$VSS_SCRIPT" ]]; then
  python3 "$VSS_SCRIPT" &
  VSS_PID=$!
  echo "VSS reader started (PID $VSS_PID)"
fi

# Start CarPlay sidecar server in the background.
# Set CARPLAY_DISABLE=1 to skip (e.g. if dongle is not yet installed).
CARPLAY_PID=""
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

exec "$BUILD_DIR/w124_cluster" --state --state-file="$W124_RUNTIME_DIR/state.json" --poll-ms=120
