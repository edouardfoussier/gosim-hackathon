#!/usr/bin/env bash
# Build the Next.js panel as a static export (``app/out/``) for Tauri.
#
# Tauri loads the frontend from a directory of static files at
# ``tauri://localhost/index.html`` — there is no Node.js runtime inside
# the .app, so the panel must build with ``output: "export"``.
#
# Strategy: temporarily swap ``app/next.config.ts`` for the export-mode
# variant, run ``pnpm build`` (which honours the swap), then restore the
# dev-mode config on exit/failure via ``trap``. This keeps the user's
# normal `pnpm dev` workflow completely untouched (no env var to
# remember, no `output:"export"` line cluttering the dev config).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/.." && pwd)"
APP_DIR="$REPO_ROOT/app"
EXPORT_CONFIG="$DESKTOP_DIR/app-overrides/next.config.ts"
LIVE_CONFIG="$APP_DIR/next.config.ts"
BACKUP_CONFIG="$APP_DIR/next.config.ts.tauri-bak"

echo "[frontend] repo root  : $REPO_ROOT"
echo "[frontend] app dir    : $APP_DIR"

if [[ ! -f "$EXPORT_CONFIG" ]]; then
  echo "[frontend] ERROR: missing export config at $EXPORT_CONFIG" >&2
  exit 1
fi

restore_config() {
  if [[ -f "$BACKUP_CONFIG" ]]; then
    mv "$BACKUP_CONFIG" "$LIVE_CONFIG"
    echo "[frontend] restored original next.config.ts"
  fi
}
trap restore_config EXIT INT TERM

echo "[frontend] swapping in static-export next.config.ts"
cp "$LIVE_CONFIG" "$BACKUP_CONFIG"
cp "$EXPORT_CONFIG" "$LIVE_CONFIG"

cd "$APP_DIR"

if [[ ! -d node_modules ]]; then
  echo "[frontend] node_modules missing — running pnpm install"
  pnpm install --frozen-lockfile
fi

# ``next build`` honours ``output: "export"`` and emits ``app/out/``.
echo "[frontend] running next build (static export)…"
pnpm build

if [[ ! -f "$APP_DIR/out/index.html" ]]; then
  echo "[frontend] ERROR: static export missing — out/index.html not found" >&2
  exit 1
fi

# Tauri serves static files from ``frontendDist`` via the ``tauri://``
# scheme — no need to copy out/ anywhere; tauri.conf.json's
# ``frontendDist = "../../app/out"`` already points at it.
echo "[frontend] DONE. Static bundle ready at $APP_DIR/out"
du -sh "$APP_DIR/out"
