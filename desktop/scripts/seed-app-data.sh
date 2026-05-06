#!/usr/bin/env bash
# Seed the packaged Xiexie.app's data directory from this repo.
#
# Tauri spawns the backend sidecar with XIEXIE_DATA_DIR pointed at
#   ~/Library/Application Support/ai.xiexie.desktop/data
# but Apple's Gatekeeper-translocation rules mean the .app can NEVER
# write inside its own bundle, so the wiki seed (data/wiki/*) +  demo
# inbox fixture + the .env with the user's API keys all have to live at
# that user-data location.
#
# This script copies them once, after a fresh build, on the developer's
# machine. For a publicly-shipped Xiexie there'd be a first-run UI that
# walks the user through entering their own keys instead.
#
# Re-runnable: cp -R uses dirs_exist_ok semantics, .env is copied with
# ``-n`` so we never clobber a manually-edited copy at the destination.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_DATA="$HOME/Library/Application Support/ai.xiexie.desktop/data"

mkdir -p "$APP_DATA"

# ── seed wiki (Margaret's persona — read by every skill) ─────────
mkdir -p "$APP_DATA/wiki"
cp -R "$REPO_ROOT/data/wiki/." "$APP_DATA/wiki/"
echo "[seed] wiki  → $APP_DATA/wiki"

# ── seed demo inbox + scam emails (read by analyze_email when MAIL_SOURCE=demo) ─
mkdir -p "$APP_DATA/demo"
cp -R "$REPO_ROOT/data/demo/." "$APP_DATA/demo/"
echo "[seed] demo  → $APP_DATA/demo"

# ── ensure the raw mutation folder exists so the linter doesn't crash ─
mkdir -p "$APP_DATA/raw/transcripts" "$APP_DATA/raw/screenshots"
echo "[seed] raw   → $APP_DATA/raw"

# ── seed .env (API keys). cp -n so a hand-edit at $APP_DATA/.env survives. ─
if [[ -f "$REPO_ROOT/.env" ]]; then
  if [[ -f "$APP_DATA/.env" ]]; then
    echo "[seed] .env  → already present at $APP_DATA/.env (NOT overwritten — edit by hand if you need to update)"
  else
    cp -n "$REPO_ROOT/.env" "$APP_DATA/.env"
    echo "[seed] .env  → $APP_DATA/.env"
  fi
else
  echo "[seed] .env  → SKIPPED (no $REPO_ROOT/.env to copy from)" >&2
fi

echo
echo "════════════════════════════════════════════════════════════════"
echo " Xiexie.app data dir is seeded."
echo
echo " Next: open Xiexie.app from Finder and grant the macOS"
echo " permission prompts (microphone, automation, screen recording)."
echo "════════════════════════════════════════════════════════════════"
