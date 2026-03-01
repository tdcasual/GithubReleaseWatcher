#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUN_DIR="${1:-}"
LATEST_FILE="artifacts/manual-qa/latest-run-dir"

if [[ -z "$RUN_DIR" ]]; then
  if [[ ! -f "$LATEST_FILE" ]]; then
    echo "No latest run found. Provide run dir manually, e.g. scripts/qa/manual_acceptance_stop.sh artifacts/manual-qa/20260301-120000" >&2
    exit 1
  fi
  RUN_DIR="$(cat "$LATEST_FILE")"
fi

PID_FILE="$RUN_DIR/watcher-web.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "PID file not found: $PID_FILE" >&2
  exit 1
fi

PID="$(cat "$PID_FILE")"
if [[ -z "$PID" ]]; then
  echo "Empty PID in $PID_FILE" >&2
  exit 1
fi

if ! kill -0 "$PID" 2>/dev/null; then
  echo "Process $PID is not running. Nothing to stop."
  exit 0
fi

kill "$PID"
for _ in {1..20}; do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Stopped watcher process $PID."
    exit 0
  fi
  sleep 0.2
done

echo "Process $PID did not exit after SIGTERM; send SIGKILL manually if needed." >&2
exit 1
