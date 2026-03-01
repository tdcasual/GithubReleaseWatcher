#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUN_DIR="${1:-}"
LATEST_FILE="artifacts/manual-qa/latest-run-dir"
TEMPLATE="docs/plans/2026-03-01-gate3-webdav-critical-flow-template.md"

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

if [[ ! -f "$TEMPLATE" ]]; then
  echo "Template not found: $TEMPLATE" >&2
  exit 1
fi

TS_LOCAL="$(date '+%Y-%m-%d %H:%M:%S %Z')"
COMMIT_HASH="$(git rev-parse --short HEAD)"
EXECUTOR="${USER:-unknown}"
OUTPUT="$RUN_DIR/gate3-report.md"

awk \
  -v ts="$TS_LOCAL" \
  -v executor="$EXECUTOR" \
  -v commit="$COMMIT_HASH" \
  -v evidence="$RUN_DIR" \
  '
  {
    if ($0 ~ /^执行日期：__________$/) {
      print "执行日期：" ts;
      next;
    }
    if ($0 ~ /^执行人：__________$/) {
      print "执行人：" executor;
      next;
    }
    if ($0 ~ /^版本\/提交：__________$/) {
      print "版本/提交：" commit;
      next;
    }
    if ($0 ~ /^证据目录：`artifacts\/manual-qa\/<timestamp>\/`$/) {
      print "证据目录：`" evidence "/`";
      next;
    }
    print;
  }
' "$TEMPLATE" > "$OUTPUT"

cat <<INFO
Gate 3 report generated:
- $OUTPUT

Filled values:
- 执行日期: $TS_LOCAL
- 执行人: $EXECUTOR
- 版本/提交: $COMMIT_HASH
- 证据目录: $RUN_DIR/
INFO
