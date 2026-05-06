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

# Idempotent fast-path: if an explicit ``XIEXIE_SKIP_FRONTEND_BUILD=1``
# env var is set, OR an already-exported ``out/index.html`` is fresh
# (newer than every page.tsx in the app), skip the rebuild. This lets
# the developer pre-build the frontend manually (sidesteps a Cargo
# subshell quirk on macOS where Next.js 15.5's ``next build`` lands
# only the 404 in ``out/`` despite reporting ``Exporting (4/4)``)
# and still run ``cargo tauri build`` end-to-end.
if [[ "${XIEXIE_SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
  echo "[frontend] XIEXIE_SKIP_FRONTEND_BUILD=1 — using existing $APP_DIR/out/"
  if [[ ! -f "$APP_DIR/out/index.html" ]]; then
    echo "[frontend] ERROR: skip flag set but $APP_DIR/out/index.html missing" >&2
    exit 1
  fi
  exit 0
fi

restore_config() {
  if [[ -f "$BACKUP_CONFIG" ]]; then
    /bin/mv -f "$BACKUP_CONFIG" "$LIVE_CONFIG"
    echo "[frontend] restored original next.config.ts"
  fi
}
trap restore_config EXIT INT TERM

echo "[frontend] swapping in static-export next.config.ts"
# Use /bin/cp explicitly because Edouard's shell aliases ``cp`` to
# ``cp -i`` — the interactive prompt would silently kill the swap
# inside cargo's non-interactive subshell, and we'd end up running
# the dev config through ``next build`` with no static export.
/bin/cp -f "$LIVE_CONFIG" "$BACKUP_CONFIG"
/bin/cp -f "$EXPORT_CONFIG" "$LIVE_CONFIG"

cd "$APP_DIR"

if [[ ! -d node_modules ]]; then
  echo "[frontend] node_modules missing — running pnpm install"
  pnpm install --frozen-lockfile
fi

# Wipe the ``.next`` cache + previous ``out/`` before every build. A
# stale cache from an earlier *dev-mode* `pnpm dev` run silently makes
# Next 15.5 emit a 4-route prerender count but only land 1 file on
# disk — Edouard hit this loop more than once and lost ~30 min to
# "why is index.html missing". Clean state every time is cheaper.
echo "[frontend] wiping .next + out cache for a clean export"
/bin/rm -rf "$APP_DIR/.next" "$APP_DIR/out"

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
