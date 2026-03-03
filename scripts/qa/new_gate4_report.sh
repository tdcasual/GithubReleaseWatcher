#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LATEST_FILE="artifacts/manual-qa/latest-run-dir"

RUN_DIR=""
STRICT=0
COMMANDS_FILE=""

usage() {
  cat <<USAGE
Usage: scripts/qa/new_gate4_report.sh [RUN_DIR] [--strict] [--commands-file FILE]

Generate Gate 4 automated regression report.

Arguments:
  RUN_DIR                Optional manual QA run directory (defaults to artifacts/manual-qa/latest-run-dir)
  --strict               Exit with code 2 when any command fails
  --commands-file FILE   Optional custom command list file (format: label|command)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=1
      shift
      ;;
    --commands-file)
      COMMANDS_FILE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$RUN_DIR" ]]; then
        RUN_DIR="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        usage
        exit 2
      fi
      ;;
  esac
done

if [[ -z "$RUN_DIR" ]]; then
  if [[ ! -f "$LATEST_FILE" ]]; then
    echo "No latest run found. Start with scripts/qa/manual_acceptance_bootstrap.sh or pass run dir manually." >&2
    exit 1
  fi
  RUN_DIR="$(cat "$LATEST_FILE")"
fi

if [[ ! -d "$RUN_DIR" ]]; then
  echo "Run dir not found: $RUN_DIR" >&2
  exit 1
fi

if [[ -n "$COMMANDS_FILE" && ! -f "$COMMANDS_FILE" ]]; then
  echo "Commands file not found: $COMMANDS_FILE" >&2
  exit 1
fi

declare -a LABELS=()
declare -a COMMANDS=()

load_default_commands() {
  LABELS=(
    "sync_vercel_public"
    "pytest_stable"
    "node_check_static"
    "smoke_api_flow"
  )
  COMMANDS=(
    "bash scripts/release/sync_vercel_public.sh"
    "python3 -m pytest -q -k \"not download_integration\""
    "for action in github_release_watcher/static/*.js deploy/vercel/public/*.js; do node --check \"\$action\"; done"
    "bash scripts/qa/smoke_api_flow.sh"
  )
}

load_commands_file() {
  LABELS=()
  COMMANDS=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    local raw="$line"
    raw="${raw#"${raw%%[![:space:]]*}"}"
    raw="${raw%"${raw##*[![:space:]]}"}"
    if [[ -z "$raw" || "${raw:0:1}" == "#" ]]; then
      continue
    fi
    if [[ "$raw" != *"|"* ]]; then
      echo "Invalid command line (missing '|'): $raw" >&2
      exit 1
    fi
    local label="${raw%%|*}"
    local cmd="${raw#*|}"
    label="${label#"${label%%[![:space:]]*}"}"
    label="${label%"${label##*[![:space:]]}"}"
    cmd="${cmd#"${cmd%%[![:space:]]*}"}"
    cmd="${cmd%"${cmd##*[![:space:]]}"}"
    if [[ -z "$label" || -z "$cmd" ]]; then
      echo "Invalid command line (empty label or command): $raw" >&2
      exit 1
    fi
    LABELS+=("$label")
    COMMANDS+=("$cmd")
  done < "$COMMANDS_FILE"

  if [[ ${#LABELS[@]} -eq 0 ]]; then
    echo "Commands file contains no executable commands: $COMMANDS_FILE" >&2
    exit 1
  fi
}

if [[ -n "$COMMANDS_FILE" ]]; then
  load_commands_file
else
  load_default_commands
fi

LOG_DIR="$RUN_DIR/gate4-logs"
REPORT_FILE="$RUN_DIR/gate4-report.md"
mkdir -p "$LOG_DIR"

declare -a EXIT_CODES=()
declare -a STATUSES=()
declare -a LOG_PATHS=()
ALL_OK=1

to_slug() {
  local input="$1"
  local slug
  slug="$(printf '%s' "$input" | tr '[:space:]/:' '___' | tr -cd 'A-Za-z0-9._-')"
  if [[ -z "$slug" ]]; then
    slug="step"
  fi
  printf '%s' "$slug"
}

for i in "${!LABELS[@]}"; do
  idx=$((i + 1))
  label="${LABELS[$i]}"
  cmd="${COMMANDS[$i]}"
  slug="$(to_slug "$label")"
  log_file="$LOG_DIR/$(printf '%02d' "$idx")-${slug}.log"

  {
    echo "# step: $idx"
    echo "# label: $label"
    echo "# command: $cmd"
    echo "# started_at: $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo
  } > "$log_file"

  set +e
  bash -lc "$cmd" >> "$log_file" 2>&1
  rc=$?
  set -e

  EXIT_CODES+=("$rc")
  LOG_PATHS+=("$log_file")
  if [[ "$rc" -eq 0 ]]; then
    STATUSES+=("PASS")
  else
    STATUSES+=("FAIL")
    ALL_OK=0
  fi
done

if [[ "$ALL_OK" -eq 1 ]]; then
  GATE4_PASS_MARK="x"
  GATE4_BLOCKED_MARK=" "
  OVERALL="PASS"
else
  GATE4_PASS_MARK=" "
  GATE4_BLOCKED_MARK="x"
  OVERALL="BLOCKED"
fi

TS_LOCAL="$(date '+%Y-%m-%d %H:%M:%S %Z')"
COMMIT_HASH="$(git rev-parse --short HEAD)"
EXECUTOR="${USER:-unknown}"

{
  echo "# Gate 4 Automated Regression Report"
  echo
  echo "Generated at: $TS_LOCAL"
  echo "Executor: $EXECUTOR"
  echo "Commit: $COMMIT_HASH"
  echo "Evidence directory: \`$RUN_DIR/\`"
  echo "Overall: **$OVERALL**"
  echo
  echo "- [$GATE4_PASS_MARK] Gate 4 pass"
  echo "- [$GATE4_BLOCKED_MARK] Gate 4 blocked"
  echo
  echo "## Step Summary"
  echo
  echo "| Step | Status | Exit Code | Log |"
  echo "|---|---|---:|---|"
  for i in "${!LABELS[@]}"; do
    idx=$((i + 1))
    label="${LABELS[$i]}"
    status="${STATUSES[$i]}"
    rc="${EXIT_CODES[$i]}"
    log_file="${LOG_PATHS[$i]}"
    rel_log="${log_file#$RUN_DIR/}"
    echo "| $idx. \`$label\` | $status | $rc | \`$rel_log\` |"
  done
  echo
  echo "## Step Logs"
  echo
  for i in "${!LABELS[@]}"; do
    idx=$((i + 1))
    label="${LABELS[$i]}"
    status="${STATUSES[$i]}"
    rc="${EXIT_CODES[$i]}"
    log_file="${LOG_PATHS[$i]}"
    rel_log="${log_file#$RUN_DIR/}"
    echo "### Step $idx: $label"
    echo
    echo "- Status: **$status**"
    echo "- Exit Code: \`$rc\`"
    echo "- Log: \`$rel_log\`"
    echo
    echo '```text'
    cat "$log_file"
    echo '```'
    echo
  done
} > "$REPORT_FILE"

echo "Gate 4 report generated:"
echo "- $REPORT_FILE"
echo "- Overall: $OVERALL"

if [[ "$ALL_OK" -eq 1 ]]; then
  exit 0
fi

if [[ "$STRICT" -eq 1 ]]; then
  exit 2
fi

exit 0
