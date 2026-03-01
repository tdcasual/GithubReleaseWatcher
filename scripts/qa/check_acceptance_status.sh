#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LATEST_FILE="artifacts/manual-qa/latest-run-dir"
CHECKLIST_FILE="docs/plans/2026-03-01-release-acceptance-checklist.md"

RUN_DIR=""
STRICT=0

usage() {
  cat <<USAGE
Usage: scripts/qa/check_acceptance_status.sh [RUN_DIR] [--strict]

Summarize Gate checklist/report status and evaluate release readiness.

Arguments:
  RUN_DIR    Optional manual QA run directory (defaults to artifacts/manual-qa/latest-run-dir when available)
  --strict   Exit with code 2 when release is not ready
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=1
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

if [[ -z "$RUN_DIR" && -f "$LATEST_FILE" ]]; then
  RUN_DIR="$(cat "$LATEST_FILE")"
fi

if [[ -n "$RUN_DIR" && ! -d "$RUN_DIR" ]]; then
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

gate_line_state() {
  local file="$1"
  local gate_prefix="$2"
  local line
  line="$(grep -E "^- \\[[xX ]\\] ${gate_prefix}" "$file" | head -n 1 || true)"
  if [[ -z "$line" ]]; then
    echo "MISSING"
    return
  fi
  if [[ "$line" =~ ^-\ \[[xX]\] ]]; then
    echo "CHECKED"
    return
  fi
  echo "UNCHECKED"
}

GATE2_REPORT=""
GATE3_REPORT=""
if [[ -n "$RUN_DIR" ]]; then
  GATE2_REPORT="$RUN_DIR/gate2-report.md"
  GATE3_REPORT="$RUN_DIR/gate3-report.md"
fi

GATE1_CHECKLIST="$(gate_line_state "$CHECKLIST_FILE" "Gate 1:")"
GATE2_CHECKLIST="$(gate_line_state "$CHECKLIST_FILE" "Gate 2:")"
GATE3_CHECKLIST="$(gate_line_state "$CHECKLIST_FILE" "Gate 3:")"
GATE4_CHECKLIST="$(gate_line_state "$CHECKLIST_FILE" "Gate 4:")"

GATE2_REPORT_STATE="MISSING"
GATE3_REPORT_STATE="MISSING"
if [[ -n "$GATE2_REPORT" ]]; then
  GATE2_REPORT_STATE="$(pair_state "$GATE2_REPORT" "Gate 2 pass" "Gate 2 blocked")"
fi
if [[ -n "$GATE3_REPORT" ]]; then
  GATE3_REPORT_STATE="$(pair_state "$GATE3_REPORT" "Gate 3 pass" "Gate 3 blocked")"
fi

echo "Acceptance status snapshot"
echo "Commit: $(git rev-parse --short HEAD)"
if [[ -n "$RUN_DIR" ]]; then
  echo "Run dir: $RUN_DIR"
else
  echo "Run dir: <not provided>"
fi
echo
echo "Checklist gates:"
echo "- Gate 1: $GATE1_CHECKLIST"
echo "- Gate 2: $GATE2_CHECKLIST"
echo "- Gate 3: $GATE3_CHECKLIST"
echo "- Gate 4: $GATE4_CHECKLIST"
echo
echo "Gate reports:"
echo "- Gate 2 report: $GATE2_REPORT_STATE"
echo "- Gate 3 report: $GATE3_REPORT_STATE"

READY=1
REASONS=""

if [[ "$GATE1_CHECKLIST" != "CHECKED" ]]; then
  READY=0
  REASONS+=$'\n'"- Checklist Gate 1 is not checked."
fi
if [[ "$GATE4_CHECKLIST" != "CHECKED" ]]; then
  READY=0
  REASONS+=$'\n'"- Checklist Gate 4 is not checked."
fi
if [[ "$GATE2_REPORT_STATE" != "PASS" ]]; then
  READY=0
  REASONS+=$'\n'"- Gate 2 report is not PASS."
fi
if [[ "$GATE3_REPORT_STATE" != "PASS" ]]; then
  READY=0
  REASONS+=$'\n'"- Gate 3 report is not PASS."
fi
if [[ "$GATE2_CHECKLIST" != "CHECKED" ]]; then
  READY=0
  REASONS+=$'\n'"- Checklist Gate 2 is not synced to checked."
fi
if [[ "$GATE3_CHECKLIST" != "CHECKED" ]]; then
  READY=0
  REASONS+=$'\n'"- Checklist Gate 3 is not synced to checked."
fi

echo
if [[ "$READY" -eq 1 ]]; then
  echo "Release readiness: READY"
  exit 0
fi

echo "Release readiness: BLOCKED"
echo "Blocking reasons:${REASONS}"

if [[ "$STRICT" -eq 1 ]]; then
  exit 2
fi

exit 0
