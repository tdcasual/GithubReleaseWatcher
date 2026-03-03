#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$ROOT/github_release_watcher/static"
DST="$ROOT/deploy/vercel/public"

for f in \
  api-client.js \
  formatters.js \
  logs-view.js \
  repos-controller.js \
  settings-controller.js \
  storage-diagnostics.js \
  batch-selectors.js \
  batch-actions.js \
  mobile-behavior.js \
  index.html \
  app.js \
  app-runtime.js \
  app-ui-utils.js \
  app-auth.js \
  app-settings-dialog.js \
  app-events.js \
  styles.css \
  repo.js \
  repo.html \
  favicon.svg; do
  cp "$SRC/$f" "$DST/$f"
  echo "synced: $f"
done
