"""SoundwaveOverlay — cursor-following "Xiexie is speaking" indicator.

Companion widget to :mod:`overlay.glyph`. While the warning glyph reacts
to ``alert`` frames on ``/ws`` (phishing / suspicious / clear), the
soundwave reacts to ``speaking`` frames emitted by the browser realtime
client whenever Marin (gpt-realtime's voice) is producing audio:

    {"type": "speaking", "state": "start", "level": 0.42}
    {"type": "speaking", "state": "stop"}

Visual: a creamy translucent pill (rgba(251,247,240,220), 32 px radius)
with five warm-amber bars dancing inside. If the WS frame includes a
``level`` we drive the bars from that RMS amplitude; otherwise each bar
runs an independent procedural sine so the wave still looks alive.

The window is **always click-through** — Margaret should never feel like
the overlay is grabbing input from Chrome / Mail / wherever she's
actually looking. We use ``Qt.WindowType.WindowTransparentForInput`` on
top of the ``WA_TransparentForMouseEvents`` flag plus a tiny 1×1 pixel
``setMask`` parked far outside the visible canvas — belt-and-braces so
the widget cannot eat clicks even if a future Qt release silently drops
one of those flags.

CLI hook for offline preview::

    python -m overlay.soundwave --duration 4 --procedural

flashes a procedural wave for 4 s without touching the backend.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Sequence

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath, QRegion
from PyQt6.QtWidgets import QApplication, QWidget

from .ns_panel import promote_to_panel


# ── geometry ──────────────────────────────────────────────────────────────
# All visual sizes were doubled for the senior-demo pass — Margaret has mild
# visual impairment and the demo is judged at 2–3 m from the screen, so
# every overlay surface needs to be roughly 2× its v1 dimensions.
WINDOW_W = 360         # was 180 (v1)
WINDOW_H = 360         # was 180 (v1)
INNER_W = 128          # was 64 (v1) — the painted pill is now 128 wide
INNER_H = 128          # was 64 (v1) — ...and 128 tall
BAR_COUNT = 5          # locked — bumping count would change the visual signature
BAR_WIDTH = 6          # was 3 (v1) — logical px (devicePixelRatio applied at paint time)
BAR_GAP = 8            # was 4 (v1)
PILL_RADIUS = 64       # was 32 (v1) — full half-height = true pill
CURSOR_OFFSET_X = 32   # unchanged — bigger pill now overlaps the cursor more (intentional)
CURSOR_OFFSET_Y = 32   # unchanged — same as above
CURSOR_FOLLOW_MS = 60  # animation cadence — unchanged per spec

# ── motion ───────────────────────────────────────────────────────────────
PROCEDURAL_FPS = 30                    # 30 fps is plenty for 5 bars
PROCEDURAL_INTERVAL_MS = 1000 // PROCEDURAL_FPS
PROCEDURAL_FREQ_HZ = 1.7               # base oscillation rate
PROCEDURAL_PHASE_STEP = 0.55           # radians between adjacent bars
PROCEDURAL_AMP = 0.55                  # baseline 0..1 for procedural bars

# Smoothing: when ``set_level`` arrives every ~100 ms we lerp the bars
# towards the target rather than snapping, so the animation reads as a
# wave rather than a strobe. ``LEVEL_SMOOTHING`` is the per-frame
# fraction of the gap to close (higher = snappier, lower = smoother).
LEVEL_SMOOTHING = 0.35
LEVEL_DECAY_PER_FRAME = 0.04           # bleeds back to procedural baseline
LEVEL_FRESHNESS_MS = 350               # treat amplitudes older than this
                                       # as stale → fall back to procedural

# ── palette (matches glyph.py for visual continuity) ─────────────────────
BAR_COLOR = QColor("#d97a25")          # ember amber
BAR_COLOR_TOP = QColor("#e89143")      # very subtle gradient highlight
PILL_FILL = QColor(251, 247, 240, 220)  # rgba(251,247,240,220) cream

# ── fade ─────────────────────────────────────────────────────────────────
FADE_IN_MS = 220
FADE_OUT_MS = 350


def _fmt_level(level: float | None) -> float | None:
    """Clamp + sanitise an inbound RMS level to ``0..1`` (or pass ``None``)."""
    if level is None:
        return None
    try:
        v = float(level)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return max(0.0, min(1.0, v))


# ── inner painted canvas ─────────────────────────────────────────────────
class _SoundwaveCanvas(QWidget):
    """The ``INNER_W × INNER_H`` widget that actually paints bars + pill.

    Bars hold their normalised heights in ``self._bars`` (a list of 5
    floats in ``0..1``). The parent overlay animates ``windowOpacity``;
    this canvas is opacity-agnostic and just paints whatever the bars
    currently say.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(INNER_W, INNER_H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._bars: list[float] = [PROCEDURAL_AMP] * BAR_COUNT

    def set_bars(self, values: Sequence[float]) -> None:
        # Defensive copy + clamp; we never want a NaN to slip into
        # ``drawRoundedRect`` and crash the painter on Retina.
        self._bars = [max(0.05, min(1.0, float(v))) for v in values][:BAR_COUNT]
        self.update()

    def paintEvent(self, event):  # noqa: N802 — Qt naming
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        try:
            self._paint_pill(painter)
            self._paint_bars(painter)
        finally:
            painter.end()

    def _paint_pill(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(PILL_FILL)
        rect = QRectF(0.0, 0.0, float(INNER_W), float(INNER_H))
        path = QPainterPath()
        path.addRoundedRect(rect, float(PILL_RADIUS), float(PILL_RADIUS))
        painter.drawPath(path)

    def _paint_bars(self, painter: QPainter) -> None:
        # Crystal-clear math: each bar is BAR_WIDTH wide, BAR_GAP between
        # neighbours, group centred horizontally inside INNER_W. Heights
        # range from a tasteful minimum (so silent bars don't disappear)
        # up to ``max_height`` so the loudest bar never hits the pill
        # rim, leaving a 6 px breathing margin top + bottom.
        group_width = BAR_COUNT * BAR_WIDTH + (BAR_COUNT - 1) * BAR_GAP
        x0 = (INNER_W - group_width) / 2.0
        cy = INNER_H / 2.0
        max_height = INNER_H - 24.0   # was 12.0 (v1) — 12 px breathing room top + bottom
        min_height = 12.0             # was 6.0 (v1) — never collapse to 0
        radius = BAR_WIDTH / 2.0      # rounded ends — auto-scales with BAR_WIDTH

        painter.setPen(Qt.PenStyle.NoPen)
        for i, normalised in enumerate(self._bars):
            h = min_height + (max_height - min_height) * normalised
            x = x0 + i * (BAR_WIDTH + BAR_GAP)
            y = cy - h / 2.0
            painter.setBrush(BAR_COLOR)
            painter.drawRoundedRect(QRectF(x, y, BAR_WIDTH, h), radius, radius)
            highlight_h = min(h * 0.35, 16.0)   # was 8.0 (v1)
            painter.setBrush(BAR_COLOR_TOP)
            painter.drawRoundedRect(
                QRectF(x, y, BAR_WIDTH, highlight_h), radius, radius
            )


# ── overlay window ───────────────────────────────────────────────────────
class SoundwaveOverlay(QWidget):
    """Transparent always-on-top window: cursor-following soundwave.

    Public API mirrors :class:`overlay.glyph.GlyphOverlay`'s lifecycle:

    - :meth:`start` — fade in, begin animating, follow the cursor.
    - :meth:`stop` — fade out and stop animating once invisible.
    - :meth:`set_level` — feed a real-time RMS amplitude; bars animate
      toward it. Values older than :data:`LEVEL_FRESHNESS_MS` are treated
      as stale and the wave falls back to the procedural sine.
    """

    def __init__(
        self,
        *,
        cursor_offset: tuple[int, int] = (CURSOR_OFFSET_X, CURSOR_OFFSET_Y),
        procedural_only: bool = False,
    ) -> None:
        # ``WindowTransparentForInput`` is the cleanest "I never want
        # mouse" flag on Qt 6.5+. Older Qt 6.x silently ignores it but
        # the WA_TransparentForMouseEvents attribute below covers us.
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.BypassWindowManagerHint
        )
        transparent_for_input = getattr(
            Qt.WindowType, "WindowTransparentForInput", None
        )
        if transparent_for_input is not None:
            flags |= transparent_for_input

        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(WINDOW_W, WINDOW_H)
        self.setWindowOpacity(0.0)

        self._cursor_offset = cursor_offset
        self._procedural_only = procedural_only

        # The painted canvas sits centred inside the larger transparent
        # window — the spare margin gives the bars room to breathe and
        # also keeps ns_panel level-promotion from clipping the pill.
        self._canvas = _SoundwaveCanvas(self)
        self._canvas.move(
            (WINDOW_W - INNER_W) // 2,
            (WINDOW_H - INNER_H) // 2,
        )

        # Belt-and-braces click-through: park the input mask in a 1×1
        # square FAR outside the painted pill so even if Qt forgets to
        # honour ``WindowTransparentForInput`` the window still has
        # essentially no hit area.
        self.setMask(QRegion(QRect(WINDOW_W - 1, WINDOW_H - 1, 1, 1)))

        # Animation state ────────────────────────────────────────
        self._phase_t = 0.0
        self._target_level: float | None = None
        self._level_received_ms: float = 0.0
        # ``_smoothed_bars`` carries the actual displayed values that
        # we lerp toward each frame — keeps the animation continuous
        # across procedural ↔ amplitude-driven transitions.
        self._smoothed_bars: list[float] = [PROCEDURAL_AMP] * BAR_COUNT

        self._tick = QTimer(self)
        self._tick.setInterval(PROCEDURAL_INTERVAL_MS)
        self._tick.timeout.connect(self._advance_frame)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(CURSOR_FOLLOW_MS)
        self._cursor_timer.timeout.connect(self._reposition)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._fade_target: float = 0.0

        self._active = False

    # ── public API ─────────────────────────────────────────────────────
    def is_active(self) -> bool:
        """``True`` while the wave is on screen / fading in (post-``start``)."""
        return self._active

    def start(self) -> None:
        """Show the soundwave and begin animating + following the cursor.

        Idempotent: repeated calls while already visible just refresh
        the fade target back to 1.0 (handy if a ``start`` arrives mid
        fade-out).
        """
        self._active = True
        self._reposition()
        if not self.isVisible():
            self.show()
            promote_to_panel(self, ignore_mouse=True)
        self._cursor_timer.start()
        self._tick.start()
        self._fade_to(1.0, FADE_IN_MS)

    def stop(self) -> None:
        """Fade out and pause animation once invisible."""
        self._active = False
        # ``_target_level`` clears so any stragglers don't immediately
        # re-light the bars on the next ``start``.
        self._target_level = None
        self._fade_to(0.0, FADE_OUT_MS)

    def set_level(self, level: float | None) -> None:
        """Feed a real-time RMS amplitude (0..1) for amplitude-driven mode."""
        if self._procedural_only:
            return
        cleaned = _fmt_level(level)
        if cleaned is None:
            return
        self._target_level = cleaned
        self._level_received_ms = time.monotonic() * 1000.0
        # Auto-show on first level if start wasn't called explicitly —
        # the realtime client emits ``state: start`` before the first
        # amplitude, but if we ever lose that frame in transit the
        # wave still appears.
        if not self._active:
            self.start()

    # ── frame loop ────────────────────────────────────────────────────
    def _advance_frame(self) -> None:
        self._phase_t += PROCEDURAL_INTERVAL_MS / 1000.0
        target_bars = self._compute_target_bars()
        # Lerp displayed values toward the target so amplitude-driven
        # mode reads as a wave, not a strobe.
        for i in range(BAR_COUNT):
            current = self._smoothed_bars[i]
            self._smoothed_bars[i] = current + (target_bars[i] - current) * LEVEL_SMOOTHING
        self._canvas.set_bars(self._smoothed_bars)

    def _compute_target_bars(self) -> list[float]:
        # Procedural sine — independent phase per bar so the wave looks
        # alive even when every amplitude is identical.
        procedural = [
            0.5 + 0.5 * math.sin(
                2.0 * math.pi * PROCEDURAL_FREQ_HZ * self._phase_t
                + i * PROCEDURAL_PHASE_STEP
            )
            * PROCEDURAL_AMP
            for i in range(BAR_COUNT)
        ]

        if self._procedural_only or self._target_level is None:
            return procedural

        # Stale amplitudes: bleed back toward the procedural baseline so
        # we never freeze at a flat-line if the browser stops sending.
        age_ms = (time.monotonic() * 1000.0) - self._level_received_ms
        if age_ms > LEVEL_FRESHNESS_MS:
            self._target_level = max(
                0.0, self._target_level - LEVEL_DECAY_PER_FRAME
            )
            if self._target_level <= 0.01:
                self._target_level = None
                return procedural

        # Amplitude-driven: pin the centre bar to the level, then taper
        # outward bars with a small procedural wiggle so the silhouette
        # isn't a boring tent shape.
        amp = self._target_level
        wiggle = [
            0.85 + 0.15 * math.sin(
                2.0 * math.pi * (PROCEDURAL_FREQ_HZ * 1.4) * self._phase_t
                + i * (PROCEDURAL_PHASE_STEP * 1.2)
            )
            for i in range(BAR_COUNT)
        ]
        # Edge bars are 60 % of centre, mid bars 85 %, centre bar 100 %.
        falloff = [0.6, 0.85, 1.0, 0.85, 0.6]
        return [max(0.05, amp * falloff[i] * wiggle[i]) for i in range(BAR_COUNT)]

    # ── geometry ──────────────────────────────────────────────────────
    def _reposition(self) -> None:
        # Place the *painted canvas* at cursor + offset, then back-solve
        # for the outer window position so the canvas sits where the
        # spec asks (bottom-right of the cursor by default).
        cursor_pos: QPoint = QCursor.pos()
        canvas_top_left_x = cursor_pos.x() + self._cursor_offset[0]
        canvas_top_left_y = cursor_pos.y() + self._cursor_offset[1]
        win_x = canvas_top_left_x - (WINDOW_W - INNER_W) // 2
        win_y = canvas_top_left_y - (WINDOW_H - INNER_H) // 2

        # Clamp inside the current screen so a cursor near the edge
        # doesn't push the wave off-screen — keep at least 8 px margin.
        screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            win_x = max(avail.left() + 8, min(avail.right() - WINDOW_W - 8, win_x))
            win_y = max(avail.top() + 8, min(avail.bottom() - WINDOW_H - 8, win_y))

        self.move(win_x, win_y)

    # ── fade plumbing ─────────────────────────────────────────────────
    def _fade_to(self, target: float, duration_ms: int) -> None:
        self._fade.stop()
        self._fade_target = target
        self._fade.setDuration(duration_ms)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(target)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._fade_target <= 0.0 and not self._active:
            self._tick.stop()
            self._cursor_timer.stop()
            self.hide()
            # Reset bars to procedural baseline so the next ``start``
            # doesn't briefly flash the amplitude from the previous turn.
            self._smoothed_bars = [PROCEDURAL_AMP] * BAR_COUNT
            self._target_level = None


# ── CLI offline preview ──────────────────────────────────────────────────
def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="overlay.soundwave",
        description="Flash the cursor-following soundwave for testing.",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=4.0,
        help="How many seconds to keep the wave on screen (default: 4).",
    )
    p.add_argument(
        "--procedural",
        action="store_true",
        help=(
            "Force procedural sine animation even if amplitudes "
            "are simulated. Useful for the offline screenshot."
        ),
    )
    p.add_argument(
        "--simulate-levels",
        action="store_true",
        help="Pulse a fake amplitude every 120 ms so set_level is exercised.",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    app = QApplication(sys.argv)

    overlay = SoundwaveOverlay(procedural_only=args.procedural)
    overlay.start()

    if args.simulate_levels and not args.procedural:
        # A meandering sine of "amplitudes" so we can eyeball the
        # smoothing behaviour offline.
        sim_t = {"v": 0.0}

        def _emit() -> None:
            sim_t["v"] += 0.12
            level = 0.5 + 0.5 * math.sin(sim_t["v"] * 2.0)
            overlay.set_level(level * 0.8)

        sim_timer = QTimer()
        sim_timer.setInterval(120)
        sim_timer.timeout.connect(_emit)
        sim_timer.start()

    duration_ms = max(500, int(args.duration * 1000))
    QTimer.singleShot(duration_ms, overlay.stop)
    QTimer.singleShot(duration_ms + FADE_OUT_MS + 200, app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
