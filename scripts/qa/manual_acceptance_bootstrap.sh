#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

HOST="127.0.0.1"
PORT="18000"
DB_PATH="v2.sqlite3"
AUTH_USERNAME="${GRW_BOOTSTRAP_USERNAME:-admin}"
AUTH_PASSWORD="${GRW_BOOTSTRAP_PASSWORD:-change-me}"

usage() {
  cat <<USAGE
Usage: scripts/qa/manual_acceptance_bootstrap.sh [--host HOST] [--port PORT] [--db-path PATH] [--auth-username USER] [--auth-password PASS]

Start V2 API server in background for manual acceptance and print evidence locations.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --db-path)
      DB_PATH="${2:-}"
      shift 2
      ;;
    --auth-username)
      AUTH_USERNAME="${2:-}"
      shift 2
      ;;
    --auth-password)
      AUTH_PASSWORD="${2:-}"
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

if [[ -z "$AUTH_USERNAME" || -z "$AUTH_PASSWORD" ]]; then
  echo "Auth username/password must be non-empty." >&2
  exit 1
fi

TS="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="artifacts/manual-qa/$TS"
LOG_FILE="$RUN_DIR/watcher-web.log"
PID_FILE="$RUN_DIR/watcher-web.pid"
LATEST_FILE="artifacts/manual-qa/latest-run-dir"

mkdir -p "$RUN_DIR"

# Use nohup + closed stdin so process survives parent shell exit in automation environments.
nohup python3 watcher.py \
  --web \
  --web-host "$HOST" \
  --web-port "$PORT" \
  --db-path "$DB_PATH" \
  --auth-username "$AUTH_USERNAME" \
  --auth-password "$AUTH_PASSWORD" >"$LOG_FILE" 2>&1 </dev/null &
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
- DB Path: $DB_PATH
- Auth Username: $AUTH_USERNAME
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
