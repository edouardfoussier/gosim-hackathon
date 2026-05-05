#!/usr/bin/env bash
# One-shot Xiexie.app + Xiexie.dmg build.
#
# Pipeline:
#
#   1. Render the brand-aligned ember-triangle icns + tray PNGs.
#   2. PyInstaller-freeze the FastAPI backend + PyQt6 overlay daemon.
#   3. Static-export the Next.js panel into ``app/out/``.
#   4. Run ``cargo tauri build`` to produce a code-signed-ready bundle.
#   5. Inject the macOS Info.plist keys Tauri can't set declaratively
#      (LSUIElement = true so the dock stays clean, and the four
#      NSXxxxUsageDescription strings the OS displays on first
#      permission prompt — without them macOS just silently denies the
#      request, which is one of the worst possible demo failure modes).
#
# Skip individual steps with --skip-{icons,python,frontend,bundle}.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_TAURI="$DESKTOP_DIR/src-tauri"
REPO_ROOT="$(cd "$DESKTOP_DIR/.." && pwd)"

SKIP_ICONS=0
SKIP_PYTHON=0
SKIP_FRONTEND=0
SKIP_BUNDLE=0
for arg in "$@"; do
  case "$arg" in
    --skip-icons)    SKIP_ICONS=1 ;;
    --skip-python)   SKIP_PYTHON=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    --skip-bundle)   SKIP_BUNDLE=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

if (( SKIP_ICONS == 0 )); then
  echo "── 1/5 icons ────────────────────────────────────────────────"
  python3 "$SCRIPT_DIR/make-icons.py"
fi

if (( SKIP_PYTHON == 0 )); then
  echo "── 2/5 python sidecars ──────────────────────────────────────"
  bash "$SCRIPT_DIR/build-python-binaries.sh"
fi

if (( SKIP_FRONTEND == 0 )); then
  echo "── 3/5 next.js static export ────────────────────────────────"
  bash "$SCRIPT_DIR/build-frontend.sh"
fi

if (( SKIP_BUNDLE == 0 )); then
  echo "── 4/5 cargo tauri build ────────────────────────────────────"
  if ! command -v cargo >/dev/null 2>&1; then
    echo "ERROR: cargo not on PATH." >&2
    echo "Install Rust + Tauri toolchain:" >&2
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" >&2
    echo "  cargo install tauri-cli --version '^2.0' --locked" >&2
    exit 1
  fi
  if ! cargo tauri --version >/dev/null 2>&1; then
    echo "[bundle] installing tauri-cli v2…"
    cargo install tauri-cli --version '^2.0' --locked
  fi
  cd "$SRC_TAURI"
  cargo tauri build
fi

# ── 5/5 patch Info.plist ────────────────────────────────────────────
APP_BUNDLE="$SRC_TAURI/target/release/bundle/macos/Xiexie.app"
APP_PLIST="$APP_BUNDLE/Contents/Info.plist"

if [[ -f "$APP_PLIST" ]]; then
  echo "── 5/5 Info.plist patches ───────────────────────────────────"

  # LSUIElement: makes Xiexie a dockless menu-bar app. We also call
  # ``set_activation_policy(Accessory)`` in main.rs as belt-and-braces
  # (in case a launchctl variant ignores the key on first launch).
  plutil -replace LSUIElement -bool true "$APP_PLIST"

  # The privacy-prompt strings macOS shows on first permission request.
  # Tauri 2 doesn't expose these declaratively yet, but Apple silently
  # denies the request if they're missing — a silent failure that would
  # be a disaster on stage.
  plutil -replace NSMicrophoneUsageDescription -string \
    "Xiexie listens for your voice commands so it can act as your AI grandchild. Audio is processed locally — nothing leaves your computer." "$APP_PLIST"
  plutil -replace NSAppleEventsUsageDescription -string \
    "Xiexie uses Apple Events to open apps, archive scam emails, set reminders, and message your family on your behalf." "$APP_PLIST"
  plutil -replace NSScreenCaptureUsageDescription -string \
    "Xiexie can read your screen when you ask it to (e.g. \"What does this say?\"). Screenshots stay on this Mac." "$APP_PLIST"
  plutil -replace NSAccessibilityUsageDescription -string \
    "Xiexie uses accessibility features to type and click on your behalf when you ask it to act on apps." "$APP_PLIST"
  plutil -replace NSInputMonitoringUsageDescription -string \
    "Xiexie listens for the Control + Option push-to-talk shortcut so you can summon it without speaking the wake-word." "$APP_PLIST"

  # Codify the bundle version Tauri picks up from tauri.conf.json so
  # ``defaults read`` always returns a tidy semver instead of an int.
  plutil -replace CFBundleShortVersionString -string "0.1.0" "$APP_PLIST"

  echo "[bundle] patched: $APP_PLIST"
else
  echo "[bundle] WARN: Info.plist not found at $APP_PLIST — skipping patch"
fi

# ── done ──────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════════════"
echo " Xiexie built."
echo
echo " App : $APP_BUNDLE"
DMG="$(ls "$SRC_TAURI"/target/release/bundle/dmg/Xiexie_*.dmg 2>/dev/null | head -n1 || true)"
if [[ -n "$DMG" ]]; then
  echo " DMG : $DMG"
fi
echo "════════════════════════════════════════════════════════════════"
