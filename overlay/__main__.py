"""``python -m overlay`` — full overlay app: connect to backend WS, listen
for events, and drive Xiexie's two on-screen surfaces.

Run it alongside the FastAPI backend (``ws://localhost:8787/ws``):

    python -m overlay                                 # default config
    python -m overlay --url ws://localhost:8787/ws    # explicit
    python -m overlay --position follow-cursor --chime
    python -m overlay --selftest                      # 3-glyph cycle, no WS

If the backend isn't running, the overlay stays alive and retries the
connection in the background — you can fire it up later without
restarting the overlay.

Two-event protocol (over ``ws://localhost:8787/ws``)::

    {"type": "alert", "level": "phishing"|"suspicious"|"clear",
     "message": "..."}
        → flashes the warning glyph (``GlyphOverlay``)

    {"type": "speaking", "state": "start"|"stop",
     "level": 0..1 | null}
        → shows / hides the cursor-following soundwave
          (``SoundwaveOverlay``). When ``level`` is provided the bars
          animate amplitude-driven; without it the wave runs a
          procedural sine fallback.

Both overlays are sibling top-level windows — never nested — so they
coexist (Xiexie can be speaking *while* a fresh phishing alert lights
up the warning glyph) and tear down independently on Ctrl-C.
"""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .glyph import GlyphOverlay
from .pointer import PointerOverlay
from .soundwave import SoundwaveOverlay
from .ws_client import DEFAULT_URL, WsBridge


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="overlay",
        description="Xiexie native macOS overlay — warning glyph + speaking soundwave.",
    )
    p.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Xiexie backend WebSocket URL (default: {DEFAULT_URL}).",
    )
    p.add_argument(
        "--position",
        choices=["top-right", "follow-cursor", "near-active-window"],
        default="top-right",
        help="Glyph positioning mode.",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Default alert display duration in seconds (default: 5).",
    )
    p.add_argument(
        "--chime",
        action="store_true",
        help="Play a soft macOS system chime on each alert.",
    )
    p.add_argument(
        "--selftest",
        action="store_true",
        help="Cycle through all three levels and exit, ignoring --url.",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    app = QApplication(sys.argv)

    overlay = GlyphOverlay(position_mode=args.position, play_chime=args.chime)
    soundwave = SoundwaveOverlay()
    pointer = PointerOverlay()
    duration_ms = max(1000, int(args.duration * 1000))

    if args.selftest:
        from .demo import _schedule_cycle

        _schedule_cycle(overlay, duration_ms, app)
        return app.exec()

    bridge = WsBridge(args.url)

    def _on_alert(level: str, message: str, _raw: dict) -> None:
        print(f"[overlay] alert level={level!r} message={message!r}")
        overlay.show_alert(level, message, duration_ms)  # type: ignore[arg-type]

    def _on_speaking(state: str, level: object, _raw: dict) -> None:
        # Keep the daemon log readable: only print state changes, not
        # every per-frame amplitude (the browser fires a level every
        # ~100 ms).
        if state == "start" and level is None:
            print("[overlay] speaking start (procedural)")
            soundwave.start()
        elif state == "start":
            # First level after a stop counts as a state change; once
            # the wave is already running we silently forward levels.
            if not soundwave.is_active():
                level_str = f"{level:.2f}" if isinstance(level, float) else "n/a"
                print(f"[overlay] speaking start (level={level_str})")
            soundwave.start()
            if isinstance(level, float):
                soundwave.set_level(level)
        elif state == "stop":
            print("[overlay] speaking stop")
            soundwave.stop()

    def _on_connection(ok: bool) -> None:
        print(f"[overlay] backend WS {'connected' if ok else 'disconnected'}")

    # ``working`` events keep the soundwave alive while a skill runs
    # silently (vision call, scam analysis, …). We piggy-back on the
    # existing soundwave in procedural mode so Margaret sees Xiexie
    # *thinking*, not frozen. A small ref-count guards against an
    # incoming ``speaking start`` overriding our "stop" while the
    # surface is still wanted by an in-flight skill.
    working_active = {"count": 0}

    def _on_working(state: str, label: object, _raw: dict) -> None:
        if state == "start":
            working_active["count"] += 1
            if not soundwave.is_active():
                hint = label if isinstance(label, str) else "thinking"
                print(f"[overlay] working start ({hint!r})")
                soundwave.start()
        elif state == "stop":
            working_active["count"] = max(0, working_active["count"] - 1)
            if working_active["count"] == 0:
                # Only release the wave if no other working/speaking
                # signal is currently driving it. The browser realtime
                # client emits its own ``speaking stop`` when the audio
                # actually fades, so the wave never gets stranded.
                print("[overlay] working stop")
                soundwave.stop()

    def _on_point(x: int, y: int, label: object, _raw: dict) -> None:
        hint = label if isinstance(label, str) else None
        print(f"[overlay] point at ({x},{y}) label={hint!r}")
        pointer.show_at(x, y, hint)

    bridge.alert.connect(_on_alert)
    bridge.speaking.connect(_on_speaking)
    bridge.working.connect(_on_working)
    bridge.point.connect(_on_point)
    bridge.connected.connect(_on_connection)
    bridge.start()
    print(f"[overlay] listening on {args.url} (Ctrl-C to quit)")

    # Tear-down: both overlays are sibling top-level windows owned by
    # this process, so cleanup just hides + lets Qt destroy them with
    # the QApplication.
    def _shutdown() -> None:
        try:
            soundwave.stop()
        except Exception:  # noqa: BLE001 — best-effort on Ctrl-C
            pass
        try:
            overlay.hide_alert()
        except Exception:  # noqa: BLE001
            pass
        try:
            pointer.hide()
        except Exception:  # noqa: BLE001
            pass
        app.quit()

    signal.signal(signal.SIGINT, lambda *_: _shutdown())

    # Qt blocks SIGINT delivery while the event loop is idle — wake it up.
    nudge = QTimer()
    nudge.start(250)
    nudge.timeout.connect(lambda: None)

    code = app.exec()
    bridge.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
