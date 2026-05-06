#!/usr/bin/env bash
# Build the two PyInstaller-frozen Python sidecars that the Tauri shell
# spawns at launch:
#
#   - xiexie-backend  (FastAPI + uvicorn on 127.0.0.1:8787)
#   - xiexie-overlay  (PyQt6 glyph daemon, --url ws://127.0.0.1:8787/ws)
#
# Both are built with `--onedir` (a launcher binary plus a `_internal/`
# tree of shared libs and pyc files). One-file mode unpacks the entire
# bundle into a temp dir on every launch — a 2–4 s tax we can't afford
# during a stage demo, on top of the latency Margaret would already feel.
#
# The resulting directories are copied into:
#   desktop/src-tauri/binaries/{xiexie-backend,xiexie-overlay}/
# where Tauri's `bundle.resources` glob picks them up at .app build time.
#
# Re-runnable: existing output dirs are wiped before each build so we
# never end up with a half-stale tree of `_internal/` shared libs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/.." && pwd)"
BINARIES_DIR="$DESKTOP_DIR/src-tauri/binaries"
BACKEND_DIR="$REPO_ROOT/backend"
OVERLAY_DIR="$REPO_ROOT/overlay"

echo "[python] repo root        : $REPO_ROOT"
echo "[python] sidecar drop dir : $BINARIES_DIR"

mkdir -p "$BINARIES_DIR"

# ── pick the right python interpreter per sidecar ──────────────────
# Each sidecar has its own venv: the backend pins faster-whisper +
# fastapi via ``uv``, the overlay pins PyQt6 via a separate
# ``overlay/.venv``. PyInstaller MUST run from the venv that owns the
# imports for the script being frozen — running both from the backend
# venv silently produces an overlay binary that ``ImportError``s on
# ``PyQt6`` at first launch. (We hit that on 2026-05-06; took 30 min
# to track down because PyInstaller swallowed the missing-module
# warning into a "WARNING: Library not found" line that scrolled past
# in the build log.)
OVERLAY_VENV_PY="$REPO_ROOT/overlay/.venv/bin/python"
if [[ ! -x "$OVERLAY_VENV_PY" ]]; then
  echo "[python] ERROR: overlay venv missing at $OVERLAY_VENV_PY" >&2
  echo "[python] create it with:  cd overlay && python3 -m venv .venv && .venv/bin/pip install PyQt6 websockets" >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  PY_BACKEND=(uv run --project "$BACKEND_DIR" python -m PyInstaller)
  PIP_INSTALL_BACKEND=(uv pip install --project "$BACKEND_DIR")
else
  PY_BACKEND=(python3 -m PyInstaller)
  PIP_INSTALL_BACKEND=(python3 -m pip install --user)
fi
PY_OVERLAY=("$OVERLAY_VENV_PY" -m PyInstaller)

# ── ensure pyinstaller is available in BOTH venvs ──────────────────
if ! "${PY_BACKEND[@]}" --version >/dev/null 2>&1; then
  echo "[python] installing pyinstaller into the backend venv"
  "${PIP_INSTALL_BACKEND[@]}" "pyinstaller>=6.10"
fi
if ! "${PY_OVERLAY[@]}" --version >/dev/null 2>&1; then
  echo "[python] installing pyinstaller into the overlay venv"
  "$OVERLAY_VENV_PY" -m pip install "pyinstaller>=6.10"
fi

build_backend() {
  echo "[python] ── building xiexie-backend ──────────────────────────"
  cd "$BACKEND_DIR"

  rm -rf build dist xiexie-backend.spec
  rm -rf "$BINARIES_DIR/xiexie-backend"

  # Hidden imports cover packages PyInstaller's static analyser can't
  # see through (uvicorn auto-loads its own subpackages; faster_whisper
  # uses dynamic ctypes to find ctranslate2; PyAutoGUI on macOS pulls
  # ``Quartz`` lazily; etc.).
  "${PY_BACKEND[@]}" \
    --onedir \
    --name xiexie-backend \
    --noconfirm \
    --noconsole \
    --collect-submodules xiexie \
    --collect-data xiexie \
    --collect-submodules uvicorn \
    --collect-submodules fastapi \
    --collect-submodules pydantic \
    --collect-submodules openai \
    --collect-submodules faster_whisper \
    --collect-data faster_whisper \
    --collect-binaries faster_whisper \
    --collect-submodules ctranslate2 \
    --collect-data ctranslate2 \
    --collect-binaries ctranslate2 \
    --collect-binaries soundfile \
    --collect-binaries sounddevice \
    --hidden-import xiexie \
    --hidden-import xiexie.main \
    --hidden-import uvicorn.logging \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import uvicorn.protocols.websockets.auto \
    --hidden-import uvicorn.lifespan.on \
    "$SCRIPT_DIR/_pyinstaller_backend_entry.py"

  cp -R dist/xiexie-backend "$BINARIES_DIR/"
  echo "[python] xiexie-backend → $BINARIES_DIR/xiexie-backend"
}

build_overlay() {
  echo "[python] ── building xiexie-overlay ──────────────────────────"
  # PyInstaller has to import the ``overlay`` package by name, which
  # means ``overlay/`` must look like a sub-directory of the cwd — not
  # the cwd itself. Run from the repo root and pass --paths so the
  # static analyser finds ``overlay.glyph`` / ``overlay.ws_client`` /
  # ``overlay.ns_panel`` cleanly.
  cd "$REPO_ROOT"

  rm -rf "$OVERLAY_DIR/build" "$OVERLAY_DIR/dist" "$OVERLAY_DIR/xiexie-overlay.spec"
  rm -rf "$REPO_ROOT/build/xiexie-overlay" "$REPO_ROOT/dist/xiexie-overlay"
  rm -rf "$BINARIES_DIR/xiexie-overlay"

  "${PY_OVERLAY[@]}" \
    --onedir \
    --name xiexie-overlay \
    --noconfirm \
    --noconsole \
    --paths "$REPO_ROOT" \
    --collect-submodules overlay \
    --collect-data overlay \
    --collect-submodules PyQt6 \
    --collect-binaries PyQt6 \
    --hidden-import overlay \
    --hidden-import overlay.__main__ \
    --hidden-import overlay.glyph \
    --hidden-import overlay.soundwave \
    --hidden-import overlay.pointer \
    --hidden-import overlay.ws_client \
    --hidden-import overlay.ns_panel \
    "$SCRIPT_DIR/_pyinstaller_overlay_entry.py"

  cp -R dist/xiexie-overlay "$BINARIES_DIR/"
  echo "[python] xiexie-overlay → $BINARIES_DIR/xiexie-overlay"
}

build_backend
build_overlay

echo
echo "[python] sanity check: starting backend with --help (3 s timeout)…"
( "$BINARIES_DIR/xiexie-backend/xiexie-backend" --help >/dev/null 2>&1 || true ) &
SANITY_PID=$!
sleep 3
kill "$SANITY_PID" 2>/dev/null || true

echo
echo "[python] DONE. Sidecars ready under $BINARIES_DIR"
ls -lh "$BINARIES_DIR"
