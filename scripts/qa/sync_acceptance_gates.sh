#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LATEST_FILE="artifacts/manual-qa/latest-run-dir"
CHECKLIST_FILE="docs/plans/2026-03-01-release-acceptance-checklist.md"
RUN_DIR=""
DRY_RUN=0

usage() {
  cat <<USAGE
Usage: scripts/qa/sync_acceptance_gates.sh [RUN_DIR] [--checklist FILE] [--dry-run]

Sync Gate 2 / Gate 3 checkbox state in release checklist from gate reports.

Rules:
  - Report PASS    -> corresponding gate checkbox becomes [x]
  - Report BLOCKED/PENDING/MISSING/CONFLICT -> corresponding gate checkbox becomes [ ]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --checklist)
      CHECKLIST_FILE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
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
    echo "No latest run found. Pass run dir explicitly." >&2
    exit 1
  fi
  RUN_DIR="$(cat "$LATEST_FILE")"
fi

if [[ ! -d "$RUN_DIR" ]]; then
  echo "Run dir not found: $RUN_DIR" >&2
  exit 1
fi
if [[ ! -f "$CHECKLIST_FILE" ]]; then
  echo "Checklist file not found: $CHECKLIST_FILE" >&2
  exit 1
fi

line_state() {
  local file="$1"
  local label="$2"
  if [[ ! -f "$file" ]]; then
    echo "missing"
    return
  fi
  if grep -Fq -- "- [x] $label" "$file" || grep -Fq -- "- [X] $label" "$file"; then
    echo "checked"
    return
  fi
  if grep -Fq -- "- [ ] $label" "$file"; then
    echo "unchecked"
    return
  fi
  echo "missing"
}

pair_state() {
  local file="$1"
  local pass_label="$2"
  local blocked_label="$3"
  local pass_state blocked_state
  pass_state="$(line_state "$file" "$pass_label")"
  blocked_state="$(line_state "$file" "$blocked_label")"

  if [[ "$pass_state" == "missing" || "$blocked_state" == "missing" ]]; then
    echo "MISSING"
    return
  fi
  if [[ "$pass_state" == "checked" && "$blocked_state" == "checked" ]]; then
    echo "CONFLICT"
    return
  fi
  if [[ "$pass_state" == "checked" ]]; then
    echo "PASS"
    return
  fi
  if [[ "$blocked_state" == "checked" ]]; then
    echo "BLOCKED"
    return
  fi
  echo "PENDING"
}

GATE2_REPORT="$RUN_DIR/gate2-report.md"
GATE3_REPORT="$RUN_DIR/gate3-report.md"
GATE2_STATE="$(pair_state "$GATE2_REPORT" "Gate 2 pass" "Gate 2 blocked")"
GATE3_STATE="$(pair_state "$GATE3_REPORT" "Gate 3 pass" "Gate 3 blocked")"

GATE2_MARK=" "
GATE3_MARK=" "
[[ "$GATE2_STATE" == "PASS" ]] && GATE2_MARK="x"
[[ "$GATE3_STATE" == "PASS" ]] && GATE3_MARK="x"

TMP_FILE="$(mktemp)"
cleanup() {
  rm -f "$TMP_FILE"
}
trap cleanup EXIT

awk -v g2="$GATE2_MARK" -v g3="$GATE3_MARK" '
  {
    line = $0
    if (line ~ /^- \[[xX ]\] Gate 2: /) sub(/^- \[[xX ]\]/, "- [" g2 "]", line)
    if (line ~ /^- \[[xX ]\] Gate 3: /) sub(/^- \[[xX ]\]/, "- [" g3 "]", line)
    print line
  }
' "$CHECKLIST_FILE" > "$TMP_FILE"

echo "Sync source:"
echo "- Run dir: $RUN_DIR"
echo "- Gate 2 report state: $GATE2_STATE"
echo "- Gate 3 report state: $GATE3_STATE"
echo "- Checklist: $CHECKLIST_FILE"

if cmp -s "$TMP_FILE" "$CHECKLIST_FILE"; then
  echo "No checklist change required."
  exit 0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "[dry-run] Proposed checklist diff:"
  diff -u "$CHECKLIST_FILE" "$TMP_FILE" || true
  exit 0
fi

cp "$TMP_FILE" "$CHECKLIST_FILE"
echo "Checklist updated:"
echo "- Gate 2 checkbox => [$GATE2_MARK]"
echo "- Gate 3 checkbox => [$GATE3_MARK]"
