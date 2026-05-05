"""PointerOverlay — Clicky-parity ghost cursor that points to a screen
location and flashes a 1-4 word label so Margaret knows *where* to
click without hunting around the page.

Driven by ``point`` frames on ``/ws``::

    {"type": "point", "x": 1240, "y": 820, "label": "the Reply button"}

Coordinates are **global macOS screen points** (top-left origin),
already translated from image space by ``backend.skills.read_screen``
using the capture geometry it tracked. We position a small frameless
transparent window at ``(x, y)`` and paint:

- A pulsing concentric ring (the "Xiexie is pointing" beat — same
  ember accent as the warning glyph and the soundwave bars).
- A short chevron tail trailing the centre toward the label flag, so
  the eye is led from the click target to the explanatory text.
- A creamy translucent label flag offset 26 px down/right of the
  centre, with a thin 1 px border. ``Fraunces`` wasn't worth the font
  asset hop — sans-serif at 13 px reads best at the user's distance
  from the screen during a demo.

Lifecycle:

- :meth:`show_at` (re)positions the window, restarts the animation,
  and arms a 4 s auto-hide timer. A second ``show_at`` while the
  pointer is still visible cancels the previous timer and fires a
  new pulse — useful when the vision model emits multiple POINTs
  in one reply.
- :meth:`hide` collapses immediately (used at app shutdown).

Click-through is enforced via the same belt-and-braces combo as
``SoundwaveOverlay``: ``WindowTransparentForInput`` flag,
``WA_TransparentForMouseEvents`` attribute, AND a 1×1 mask parked
off-canvas.

CLI hook for offline preview::

    python -m overlay.pointer --x 800 --y 500 --label "Reply" --duration 5
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Sequence

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
)
from PyQt6.QtWidgets import QApplication, QWidget

from .ns_panel import promote_to_panel


# ── geometry ──────────────────────────────────────────────────────────────
# The window is square and centred on the target. We need enough room
# for the outermost expanding ring plus the label flag offset.
WINDOW_SIZE = 280
RING_BASE_RADIUS = 12.0
RING_MAX_RADIUS = 36.0
RING_COUNT = 3
LABEL_OFFSET = QPoint(28, 28)  # bottom-right of the centre, like a real cursor

# Visual palette — matches the ember accent the rest of the surfaces use.
EMBER_PRIMARY = QColor("#B05826")   # warm orange-brown
EMBER_DEEP = QColor("#7A381A")      # darker for the chevron tail
CREAM_BG = QColor(251, 247, 240, 235)
INK = QColor("#3D2A1B")             # near-black for label text

# Animation tempo.
PULSE_PERIOD_MS = 1100
DEFAULT_DURATION_MS = 4000
FADE_OUT_MS = 320
FRAME_INTERVAL_MS = 16  # ~60 fps


class PointerOverlay(QWidget):
    """Frameless click-through window that paints a pointing cursor at
    a global screen position and fades after ``DEFAULT_DURATION_MS``.

    Design parity with :class:`overlay.soundwave.SoundwaveOverlay` and
    :class:`overlay.glyph.GlyphOverlay` — same ember palette, same
    cream background, same NSPanel promotion so the surface stays on
    top of every Space without taking focus.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )

        # Belt-and-braces click-through: a 1×1 mask parked outside the
        # viewport so even if Qt forgets the input-transparency flag in
        # a future release we still don't eat clicks.
        self.setMask(QRegion(-10, -10, 1, 1))

        self.resize(WINDOW_SIZE, WINDOW_SIZE)
        self._label: str | None = None
        self._target: QPoint = QPoint(-WINDOW_SIZE * 2, -WINDOW_SIZE * 2)
        self._anim_t0: float = 0.0
        self._duration_ms: int = DEFAULT_DURATION_MS
        self._opacity: float = 0.0

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(FRAME_INTERVAL_MS)
        self._frame_timer.timeout.connect(self._on_frame)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self._font = QFont("Inter", 13, QFont.Weight.DemiBold)
        # AppKit fallback for hosts without Inter installed.
        self._font.setStyleHint(QFont.StyleHint.SansSerif)

    # ── public API ────────────────────────────────────────────────────
    def show_at(
        self,
        x: int,
        y: int,
        label: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Position the window centred on ``(x, y)`` (global screen
        points) and (re)start the pulse animation.
        """
        self._label = (label or "").strip() or None
        self._target = QPoint(int(x), int(y))
        self._duration_ms = duration_ms or DEFAULT_DURATION_MS

        # Centre the window on the target. Qt expects top-left.
        top_left_x = self._target.x() - WINDOW_SIZE // 2
        top_left_y = self._target.y() - WINDOW_SIZE // 2
        self.move(top_left_x, top_left_y)

        self._anim_t0 = time.perf_counter()
        self._opacity = 0.0

        # macOS panel promotion is idempotent and only meaningful once
        # the window has a native handle — call it after the first
        # ``show()``. We re-call on every ``show_at`` because reshowing
        # after auto-hide can rebuild the native window in some Qt
        # builds.
        self.show()
        promote_to_panel(self)
        self.raise_()

        self._frame_timer.start()
        self._hide_timer.start(self._duration_ms)

    def hide(self) -> None:  # type: ignore[override]
        self._frame_timer.stop()
        self._hide_timer.stop()
        super().hide()

    # ── animation tick ────────────────────────────────────────────────
    def _on_frame(self) -> None:
        elapsed_ms = (time.perf_counter() - self._anim_t0) * 1000.0
        # Fade in over the first 180 ms, fade out over the last
        # FADE_OUT_MS, stay at 1.0 in between.
        fade_in = min(1.0, elapsed_ms / 180.0)
        remaining = self._duration_ms - elapsed_ms
        fade_out = max(0.0, min(1.0, remaining / FADE_OUT_MS))
        self._opacity = max(0.0, min(1.0, fade_in * fade_out))
        self.update()
        if remaining <= 0:
            self.hide()

    # ── painting ──────────────────────────────────────────────────────
    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setOpacity(self._opacity)

        # The widget's local origin is the top-left of the window, but
        # our anchor is the *centre* (where the pointer points).
        cx = WINDOW_SIZE / 2
        cy = WINDOW_SIZE / 2

        elapsed = time.perf_counter() - self._anim_t0
        phase = (elapsed * 1000.0 % PULSE_PERIOD_MS) / PULSE_PERIOD_MS  # 0..1

        # ── concentric expanding rings ────────────────────────────────
        for ring_idx in range(RING_COUNT):
            ring_phase = (phase + ring_idx / RING_COUNT) % 1.0
            radius = RING_BASE_RADIUS + ring_phase * (
                RING_MAX_RADIUS - RING_BASE_RADIUS
            )
            ring_alpha = int((1.0 - ring_phase) * 200)
            color = QColor(EMBER_PRIMARY)
            color.setAlpha(ring_alpha)
            pen = QPen(color, 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        # ── solid centre dot ──────────────────────────────────────────
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(EMBER_PRIMARY)
        painter.drawEllipse(QRectF(cx - 5.5, cy - 5.5, 11, 11))

        # ── chevron tail leading the eye to the label ────────────────
        # Triangle pointing toward the label offset (down-right).
        tail = QPainterPath()
        # Three-stop "comet" trail: start at centre offset 6 px in the
        # chevron direction, then a wider triangular blob.
        tail_start_x = cx + 7
        tail_start_y = cy + 7
        tail.moveTo(tail_start_x, tail_start_y)
        tail.lineTo(tail_start_x + 14, tail_start_y + 4)
        tail.lineTo(tail_start_x + 4, tail_start_y + 14)
        tail.closeSubpath()
        painter.setBrush(EMBER_DEEP)
        painter.drawPath(tail)

        # ── label flag ────────────────────────────────────────────────
        if self._label:
            painter.setFont(self._font)
            metrics = QFontMetrics(self._font)
            text_w = metrics.horizontalAdvance(self._label)
            text_h = metrics.height()
            pad_x, pad_y = 10, 6
            flag_w = text_w + pad_x * 2
            flag_h = text_h + pad_y * 2
            flag_x = cx + LABEL_OFFSET.x()
            flag_y = cy + LABEL_OFFSET.y()
            # Keep the flag inside the window — clamp if the offset
            # would push it past the bottom-right edge.
            flag_x = min(flag_x, WINDOW_SIZE - flag_w - 4)
            flag_y = min(flag_y, WINDOW_SIZE - flag_h - 4)

            flag_rect = QRectF(flag_x, flag_y, flag_w, flag_h)
            painter.setBrush(CREAM_BG)
            painter.setPen(QPen(EMBER_PRIMARY, 1.0))
            painter.drawRoundedRect(flag_rect, 10, 10)

            painter.setPen(QPen(INK))
            painter.drawText(flag_rect, Qt.AlignmentFlag.AlignCenter, self._label)

        painter.end()


def _selftest_cycle(
    overlay: PointerOverlay, app: QApplication
) -> None:
    """Cycle through three points so the painter is exercised on real
    pixels — used by ``python -m overlay.pointer --selftest``.
    """
    screen = app.primaryScreen()
    if screen is None:
        return
    geo = screen.geometry()
    points = [
        (geo.x() + geo.width() // 4, geo.y() + geo.height() // 4, "top-left"),
        (geo.x() + geo.width() // 2, geo.y() + geo.height() // 2, "centre"),
        (
            geo.x() + 3 * geo.width() // 4,
            geo.y() + 3 * geo.height() // 4,
            "the Reply button",
        ),
    ]

    def fire(idx: int) -> None:
        if idx >= len(points):
            QTimer.singleShot(800, app.quit)
            return
        x, y, label = points[idx]
        overlay.show_at(x, y, label, duration_ms=2200)
        QTimer.singleShot(2400, lambda: fire(idx + 1))

    QTimer.singleShot(200, lambda: fire(0))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="overlay.pointer")
    p.add_argument("--x", type=int, default=400)
    p.add_argument("--y", type=int, default=300)
    p.add_argument("--label", default="click here")
    p.add_argument("--duration", type=float, default=4.0)
    p.add_argument(
        "--selftest",
        action="store_true",
        help="Cycle through three preset points on the primary screen.",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    app = QApplication(sys.argv)
    overlay = PointerOverlay()
    if args.selftest:
        _selftest_cycle(overlay, app)
    else:
        overlay.show_at(args.x, args.y, args.label, int(args.duration * 1000))
        QTimer.singleShot(int((args.duration + 0.4) * 1000), app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
