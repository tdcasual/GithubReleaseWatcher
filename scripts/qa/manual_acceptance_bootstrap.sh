#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

CONFIG_FILE="config.toml"
HOST="127.0.0.1"
PORT="18000"

usage() {
  cat <<USAGE
Usage: scripts/qa/manual_acceptance_bootstrap.sh [--config FILE] [--host HOST] [--port PORT]

Start watcher web UI in background for manual acceptance and print evidence locations.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_FILE="${2:-}"
      shift 2
      ;;
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Config file not found: $CONFIG_FILE" >&2
  echo "Tip: copy config.example.toml to config.toml first, then retry." >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="artifacts/manual-qa/$TS"
LOG_FILE="$RUN_DIR/watcher-web.log"
PID_FILE="$RUN_DIR/watcher-web.pid"
LATEST_FILE="artifacts/manual-qa/latest-run-dir"

mkdir -p "$RUN_DIR"

# Use nohup + closed stdin so process survives parent shell exit in automation environments.
nohup python3 watcher.py --config "$CONFIG_FILE" --web --web-host "$HOST" --web-port "$PORT" >"$LOG_FILE" 2>&1 </dev/null &
PID="$!"
echo "$PID" > "$PID_FILE"
echo "$RUN_DIR" > "$LATEST_FILE"

sleep 1
if ! kill -0 "$PID" 2>/dev/null; then
  echo "Watcher failed to start. Recent log:" >&2
  tail -n 40 "$LOG_FILE" >&2 || true
  exit 1
fi

cat <<INFO
Manual acceptance environment is ready.

- URL: http://$HOST:$PORT/
- PID: $PID
- Log: $LOG_FILE
- Evidence root: $RUN_DIR

Gate 2 docs:
- docs/plans/2026-03-01-gate2-device-acceptance-kit.md
- docs/plans/2026-03-01-gate2-device-acceptance-template.md

Gate 3 docs:
- docs/plans/2026-03-01-gate3-webdav-critical-flow-runbook.md

Stop command:
- scripts/qa/manual_acceptance_stop.sh
INFO
