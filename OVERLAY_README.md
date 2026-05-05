# Xiexie native overlay (macOS)

> A tiny always-on-top floating warning glyph that lights up over **any**
> macOS application when the Xiexie backend signals a scam/phishing
> verdict. PyQt6 + transparent QWidget + PyObjC NSPanel tweak.
> Inspired by Clicky's blue companion cursor — used for **warning**
> instead of guidance.

**Branch:** `feat/native-overlay`
**Stack picked:** PyQt6 (option 1 from the brief). Verdict: **feasible-and-prototyped**.

---

## TL;DR (60-second demo)

```bash
# from repo root, in the worktree:
cd /Users/edouardfoussier/code/gosim-hack-overlay

# create venv + install deps (one-off)
uv venv --python 3.11 overlay/.venv
source overlay/.venv/bin/activate
uv pip install PyQt6 websockets pyobjc-framework-Cocoa

# (1) Offline glyph test — should flash a red triangle in the top-right
python -m overlay.demo --level phishing

# (2) Cycle through all three levels
python -m overlay.demo --cycle --duration 3

# (3) Full overlay listening to the (mock) backend WS
python -m overlay._mock_ws &        # tiny stand-in for the FastAPI WS
python -m overlay                   # connects, glyph flashes on each alert
```

---

## What it does

1. **Always-on-top transparent panel** that floats above every other
   window — including fullscreen apps and Mission Control Spaces.
2. **Click-through everywhere except the glyph itself** — your typing,
   scrolling, and clicks pass straight to whatever app is underneath.
3. **Three alert levels** with distinct visual language:
   - `phishing` → red triangle, **!**
   - `suspicious` → amber circle, **?**
   - `clear` → green circle, **✓**
4. **Three positioning modes:**
   - `top-right` (default, safe for demo)
   - `follow-cursor` (Clicky-style; repositions every 60 ms)
   - `near-active-window` (placeholder — see *Known limitations*)
5. **Soft fade-in / fade-out** (220 ms `QPropertyAnimation` on
   `windowOpacity`) and **5 s default auto-hide**.
6. **Click-to-dismiss** — clicking the glyph hides it immediately and
   emits a `dismissed(level)` Qt signal.
7. **Optional system chime** (`afplay /System/Library/Sounds/...`):
   `Sosumi.aiff` for phishing, `Funk.aiff` for suspicious, `Glass.aiff`
   for clear. Off by default (`--chime` to enable).
8. **WebSocket-driven**: connects to the same `ws://localhost:8787/ws`
   the Next.js app uses. Reconnects with exponential backoff if the
   backend isn't running yet — you can start the overlay first.
9. **Spaces-survival via PyObjC**: after the QWidget is shown we reach
   into the underlying `NSWindow` and set
   `setLevel_(NSStatusWindowLevel)` plus
   `setCollectionBehavior_(CanJoinAllSpaces | StationaryFanInOut |
   FullScreenAuxiliary)`.

---

## Architecture (~310 lines of Python total)

```
overlay/
├── __init__.py        — package marker, version
├── __main__.py        — `python -m overlay`: WS-listening daemon (~90 LOC)
├── glyph.py           — GlyphOverlay QWidget, themes, masking, animation (~290 LOC)
├── ns_panel.py        — PyObjC bridge to make the NSWindow act like a panel (~60 LOC)
├── ws_client.py       — async WS bridge running in a daemon thread,
│                        forwards `{type:"alert"}` to a Qt signal (~95 LOC)
├── demo.py            — `python -m overlay.demo --level phishing` (~85 LOC)
├── _mock_ws.py        — local FastAPI-stand-in for offline e2e tests (~55 LOC)
└── pyproject.toml     — declares `xiexie-overlay` and CLI entry points
```

**Threading model:**
- Main thread: `QApplication` event loop, paint, mouse, NS window.
- Worker thread (daemon): `asyncio` event loop running `websockets`.
  Decoded `alert` payloads cross threads via `pyqtSignal` — Qt does
  the queued cross-thread delivery for us.

**Click-through implementation:** instead of `WA_TransparentForMouseEvents`
(which would also block clicks on the glyph), the QWidget uses
`setMask(QRegion)` set to the glyph polygon. Mouse events outside the
mask fall through to the underlying app; events inside hit our
`mousePressEvent`.

**Backend contract** (already documented for the future hook):

```json
{ "type": "alert",
  "level": "phishing" | "suspicious" | "clear",
  "message": "free-form string shown in logs (and one day in a tooltip)" }
```

The overlay ignores every other message type the backend currently
emits (`transcript`, `speak`, `confirm`, `skill_*`, `done`).

---

## How to test

### 1. Pure-overlay smoke test (no backend, no WS)

```bash
source overlay/.venv/bin/activate
python -m overlay.demo --level phishing                # red triangle, top-right, 5s
python -m overlay.demo --level suspicious --chime      # amber circle + soft chime
python -m overlay.demo --level clear --duration 3      # green check, 3s
python -m overlay.demo --cycle --duration 2            # all three back-to-back
python -m overlay.demo --level phishing --position follow-cursor
```

Each command exits cleanly when the auto-hide fade finishes.

### 2. End-to-end WS test (using the bundled mock)

Terminal A (mock backend, prints `[mock-ws] sent ...` every 2.5 s):
```bash
python -m overlay._mock_ws
```

Terminal B (overlay):
```bash
python -m overlay
```

Expected log on B:
```
[overlay] listening on ws://localhost:8787/ws (Ctrl-C to quit)
[overlay] backend WS connected
[overlay] alert level='phishing' message='Mock alert: this email looks like phishing.'
[overlay] alert level='suspicious' message='Mock alert: a link in this email looks risky.'
[overlay] alert level='clear' message='Mock alert: this email looks safe.'
```

### 3. End-to-end with the *real* FastAPI backend

The current backend's `/ws` does **not** emit `alert` events yet — that's
the next change. To produce one for testing, drop this snippet anywhere
in the existing `/ws` handler (e.g. after the planner returns a
high-confidence phishing verdict):

```python
await ws.send_json({
    "type": "alert",
    "level": "phishing",
    "message": "Aetnna-secure typosquat — 4-hop redirect to .ru",
})
```

The overlay will react instantly. Until that hook is wired, use
`overlay._mock_ws` for the demo flow.

---

## Known limitations & what 1–2 h of polish would buy

| Area | Today | 1–2 h polish |
| --- | --- | --- |
| `near-active-window` mode | Stub: same as `top-right`. | Use the macOS Accessibility API (`AXUIElementCopyAttributeValue` via PyObjC) to read the focused window's bounds and anchor relative to it. |
| Click-through edges | `setMask(QRegion)` is a binary mask → triangle/circle edges are aliased (1 px stair-stepping). | Render the glyph into an offscreen `QImage` with full alpha, then derive a soft mask via a 2 px erosion. Native macOS shadow + smoother edges. |
| Multi-monitor | Always anchors to `primaryScreen()`. | Use the screen containing the active window; expose `--screen <index>`. |
| Permissions UX | Mic/Accessibility prompts come from the **backend** process, not the overlay. The overlay needs none — but a first-run banner could explain that. | Add a one-shot first-run dialog that links to System Settings > Privacy. |
| Tooltip / message body | The `message` from the backend is logged but not shown. | Add a small frosted-glass NSVisualEffectView panel under the glyph showing the first ~40 chars; keep it click-through. |
| Audio | Uses `afplay` on built-in `.aiff` files (off by default). | Bundle a custom 0.4 s WAV per level (richer than system sounds) and play via `QSoundEffect` for lower latency. |
| Packaging | Runs from venv. No `.app` bundle yet. | `py2app` or `briefcase` build → drag-installable `Xiexie Overlay.app` with a menu-bar icon. ~2 h. |
| Dock icon | Visible because we're a regular `QApplication`. | Set `LSUIElement = True` in the bundled `Info.plist` so the overlay runs as an accessory app (no Dock entry, no `Cmd-Tab`). |
| Reconnect feedback | Logs to stderr only. | Tiny menu-bar status item (`NSStatusItem`) with green/grey dot. |

---

## Why PyQt6 (not PyObjC, not Tauri)

- **PyObjC + NSPanel** is "most native" but ~3× the code; we'd have to
  hand-roll a `NSView` with custom `drawRect:`, `mouseDown:`, and a
  Cocoa run loop bridge to `asyncio`. Worth doing for v2; overkill for
  a 4-h prototype.
- **Tauri v2 + `tauri-nspanel`** would have been the prettiest path but
  (a) `cargo` isn't installed on this Mac (would burn ≥1 h on the Rust
  toolchain), and (b) tauri-apps/tauri#13070 documents real
  click-through limitations on macOS today. Re-evaluate post-hackathon.
- **Electron** — explicitly forbidden in the brief and rightly so.
- **PyQt6** — Edouard already knows Python, the dep tree is just
  `PyQt6 + websockets + pyobjc-framework-Cocoa` (a ~75 MB venv on
  Apple Silicon), and the `pip install` ran in 90 s on first contact.
  Click-through and Spaces-survival both work without C extensions.

---

## Quick reference

```bash
# Activate venv
source overlay/.venv/bin/activate

# Single-shot glyph
python -m overlay.demo --level {phishing,suspicious,clear} \
                      [--message "..."] [--duration N] \
                      [--position {top-right,follow-cursor,near-active-window}] \
                      [--chime]

# Cycle test
python -m overlay.demo --cycle --duration 3

# Full overlay
python -m overlay [--url ws://localhost:8787/ws] \
                  [--position ...] [--duration N] [--chime] \
                  [--selftest]

# Mock backend (for offline e2e)
python -m overlay._mock_ws
```
