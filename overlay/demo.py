"""Tiny CLI to flash the overlay glyph for testing without a backend.

Examples::

    python -m overlay.demo --level phishing
    python -m overlay.demo --level suspicious --duration 8 --position follow-cursor
    python -m overlay.demo --level clear --chime
    python -m overlay.demo --cycle           # phishing → suspicious → clear, 4s each

Run this without any FastAPI backend to validate the overlay end-to-end.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .glyph import GlyphOverlay


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="overlay.demo",
        description="Flash the Xiexie warning glyph for testing.",
    )
    p.add_argument(
        "--level",
        choices=["phishing", "suspicious", "clear"],
        default=None,
        help="Single-shot alert level (default: cycle through all three).",
    )
    p.add_argument(
        "--message",
        default="",
        help="Optional message attached to the alert (empty = glyph alone, no tooltip pill).",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="How many seconds to keep each glyph on screen (default: 5).",
    )
    p.add_argument(
        "--position",
        choices=["top-right", "follow-cursor", "near-active-window"],
        default="top-right",
        help="Glyph positioning mode (default: top-right).",
    )
    p.add_argument(
        "--chime",
        action="store_true",
        help="Play a soft macOS system chime on each alert.",
    )
    p.add_argument(
        "--cycle",
        action="store_true",
        help="Cycle through all three levels back-to-back, then exit.",
    )
    return p.parse_args(argv)


def _schedule_cycle(overlay: GlyphOverlay, duration_ms: int, app: QApplication) -> None:
    levels = ["phishing", "suspicious", "clear"]
    # Stagger calls so each glyph gets its own ``duration_ms`` window.
    for i, level in enumerate(levels):
        QTimer.singleShot(
            i * duration_ms,
            lambda lvl=level: overlay.show_alert(lvl, f"Cycle demo: {lvl}", duration_ms),
        )
    # Quit shortly after the last glyph fades out.
    QTimer.singleShot(len(levels) * duration_ms + 800, app.quit)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    app = QApplication(sys.argv)

    overlay = GlyphOverlay(position_mode=args.position, play_chime=args.chime)
    duration_ms = max(1000, int(args.duration * 1000))

    if args.cycle or args.level is None:
        _schedule_cycle(overlay, duration_ms, app)
    else:
        overlay.show_alert(args.level, args.message, duration_ms)
        # Quit a bit after the auto-hide so the fade-out animation finishes.
        QTimer.singleShot(duration_ms + 800, app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
