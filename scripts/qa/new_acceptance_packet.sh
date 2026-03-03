#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

RUN_DIR="${1:-}"
LATEST_FILE="artifacts/manual-qa/latest-run-dir"

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

GATE2_SCRIPT="$ROOT_DIR/scripts/qa/new_gate2_report.sh"
GATE3_SCRIPT="$ROOT_DIR/scripts/qa/new_gate3_report.sh"
GATE4_SCRIPT="$ROOT_DIR/scripts/qa/new_gate4_report.sh"

if [[ ! -x "$GATE2_SCRIPT" || ! -x "$GATE3_SCRIPT" || ! -x "$GATE4_SCRIPT" ]]; then
  echo "Required scripts missing or not executable:" >&2
  echo "- $GATE2_SCRIPT" >&2
  echo "- $GATE3_SCRIPT" >&2
  echo "- $GATE4_SCRIPT" >&2
  exit 1
fi

"$GATE2_SCRIPT" "$RUN_DIR" >/dev/null
"$GATE3_SCRIPT" "$RUN_DIR" >/dev/null
"$GATE4_SCRIPT" "$RUN_DIR" >/dev/null

TS_LOCAL="$(date '+%Y-%m-%d %H:%M:%S %Z')"
COMMIT_HASH="$(git rev-parse --short HEAD)"
PACKET_FILE="$RUN_DIR/release-acceptance-packet.md"
WATCHER_LOG="$RUN_DIR/watcher-web.log"

cat > "$PACKET_FILE" <<INFO
# Release Acceptance Packet

Generated at: $TS_LOCAL
Commit: $COMMIT_HASH
Evidence directory: \
\`$RUN_DIR/\`

## Included Files

- \`$RUN_DIR/gate2-report.md\`
- \`$RUN_DIR/gate3-report.md\`
- \`$RUN_DIR/gate4-report.md\`
- \`$WATCHER_LOG\` $( [[ -f "$WATCHER_LOG" ]] && echo "(exists)" || echo "(not found yet)" )

## Execution Order

1. Fill Gate 2 report: \`$RUN_DIR/gate2-report.md\`
2. Fill Gate 3 report: \`$RUN_DIR/gate3-report.md\`
3. Review Gate 4 report: \`$RUN_DIR/gate4-report.md\`
3. Sync conclusion into:
   - \`docs/plans/2026-03-01-release-acceptance-checklist.md\`

## Final Gate Update Checklist

- [ ] Gate 2 status updated in release checklist
- [ ] Gate 3 status updated in release checklist
- [ ] Gate 4 status updated in release checklist
- [ ] P1/P2 defects reviewed and status confirmed
- [ ] Evidence screenshots/log references attached
INFO

cat <<DONE
Acceptance packet generated:
- $PACKET_FILE

Generated reports:
- $RUN_DIR/gate2-report.md
- $RUN_DIR/gate3-report.md
- $RUN_DIR/gate4-report.md

Next step:
1) Open Gate2/Gate3 reports and review Gate4 report.
2) Sync gate results back to docs/plans/2026-03-01-release-acceptance-checklist.md
DONE
