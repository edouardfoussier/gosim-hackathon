"""``python -m overlay`` — full overlay app: connect to backend WS, listen
for alerts, and flash the glyph.

Run it alongside the FastAPI backend (``ws://localhost:8787/ws``):

    python -m overlay                                 # default config
    python -m overlay --url ws://localhost:8787/ws    # explicit
    python -m overlay --position follow-cursor --chime
    python -m overlay --selftest                      # 3-glyph cycle, no WS

If the backend isn't running, the overlay stays alive and retries the
connection in the background — you can fire it up later without
restarting the overlay.
"""

from __future__ import annotations

import argparse
import signal
import sys
from typing import Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .glyph import GlyphOverlay
from .ws_client import DEFAULT_URL, WsBridge


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="overlay",
        description="Xiexie native macOS overlay glyph.",
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
    duration_ms = max(1000, int(args.duration * 1000))

    if args.selftest:
        from .demo import _schedule_cycle

        _schedule_cycle(overlay, duration_ms, app)
        return app.exec()

    bridge = WsBridge(args.url)

    def _on_alert(level: str, message: str, _raw: dict) -> None:
        print(f"[overlay] alert level={level!r} message={message!r}")
        overlay.show_alert(level, message, duration_ms)  # type: ignore[arg-type]

    def _on_connection(ok: bool) -> None:
        print(f"[overlay] backend WS {'connected' if ok else 'disconnected'}")

    bridge.alert.connect(_on_alert)
    bridge.connected.connect(_on_connection)
    bridge.start()
    print(f"[overlay] listening on {args.url} (Ctrl-C to quit)")

    # Handle Ctrl-C gracefully when launched from a terminal.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # Qt blocks SIGINT delivery while the event loop is idle — wake it up.
    nudge = QTimer()
    nudge.start(250)
    nudge.timeout.connect(lambda: None)

    code = app.exec()
    bridge.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
