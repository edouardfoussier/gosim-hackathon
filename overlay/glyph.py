"""GlyphOverlay — transparent floating warning glyph for Xiexie's macOS overlay.

Three alert levels with distinct visual + motion language:

- ``phishing`` — rounded crimson triangle, white "!", slow pulsing outer
  glow (1.4 s loop) drawing the eye without being startling.
- ``suspicious`` — amber circle, white "?", gentle 2 s vertical bob so
  the user notices it on motion-detection wetware alone.
- ``clear`` — forest-green circle, white check mark, no animation: the
  visual equivalent of a quiet nod.

When ``message`` is non-empty in the WS payload, a small frosted pill
floats below the glyph showing the message in 14 pt cream-white text
(``#fbf7f0``) on ``rgba(0, 0, 0, 180)``.

The glyph itself is rendered into an offscreen ``QPixmap`` with full
alpha — the parent overlay paints nothing — so the antialiased edges of
the triangle / circle never touch a 1-bit ``QRegion`` mask. Click-through
outside the glyph + tooltip area is preserved via a generous *outside*
``setMask`` (the mask sits in fully-transparent area where it can't
introduce visible stair-stepping on the painted shape).
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QLabel,
    QWidget,
)

from .ns_panel import promote_to_panel

AlertLevel = Literal["phishing", "suspicious", "clear"]
PositionMode = Literal["top-right", "follow-cursor", "near-active-window"]


# ── brand palette ───────────────────────────────────────────────────────
# Warm "ember" amber primary, creamy off-white surfaces — never pure black
# or pure white.  See the design polish pass brief for context.
BRAND_AMBER = QColor("#d97a25")
BRAND_CREAM = QColor("#fbf7f0")
BRAND_FOREST = QColor("#2f6d3f")
BRAND_CRIMSON = QColor("#b8351c")


@dataclass(frozen=True)
class GlyphTheme:
    fill: QColor
    border: QColor
    glow: QColor | None  # ``None`` → no outer glow / pulse
    symbol_color: QColor
    symbol: str
    shape: Literal["triangle", "circle"]
    label: str


THEMES: dict[str, GlyphTheme] = {
    "phishing": GlyphTheme(
        fill=BRAND_CRIMSON,
        border=QColor("#7a1f10"),
        glow=BRAND_CRIMSON,
        symbol_color=BRAND_CREAM,
        symbol="!",
        shape="triangle",
        label="Phishing",
    ),
    "suspicious": GlyphTheme(
        fill=BRAND_AMBER,
        border=QColor("#8a4316"),
        glow=None,
        symbol_color=BRAND_CREAM,
        symbol="?",
        shape="circle",
        label="Suspicious",
    ),
    "clear": GlyphTheme(
        fill=BRAND_FOREST,
        border=QColor("#1f4828"),
        glow=None,
        symbol_color=BRAND_CREAM,
        symbol="✓",
        shape="circle",
        label="Clear",
    ),
}

# Final glyph footprint: 64×64 (was ~48 — bumped for senior visibility).
# The window itself is much larger so the pulsing glow and the tooltip
# pill have room to breathe without their bounding rect leaking out.
GLYPH_INNER = 64
GLOW_PAD = 32          # extra room around the glyph for the soft glow
TOOLTIP_GAP = 14       # space between the glyph and the tooltip pill
WINDOW_W = 360
WINDOW_H = 220


# ── geometry helpers ───────────────────────────────────────────────────
def _rounded_polygon(points: list[QPointF], radius: float) -> QPainterPath:
    """Build a closed ``QPainterPath`` that traces ``points`` with rounded
    corners. Uses a quadratic bezier at every vertex so the curvature is
    visually identical to CSS ``border-radius`` on a polygon.
    """
    n = len(points)
    path = QPainterPath()
    for i in range(n):
        curr = points[i]
        prev = points[(i - 1) % n]
        nxt = points[(i + 1) % n]
        v_in = QPointF(prev.x() - curr.x(), prev.y() - curr.y())
        v_out = QPointF(nxt.x() - curr.x(), nxt.y() - curr.y())
        l_in = math.hypot(v_in.x(), v_in.y()) or 1.0
        l_out = math.hypot(v_out.x(), v_out.y()) or 1.0
        r = min(radius, l_in / 2.0, l_out / 2.0)
        in_pt = QPointF(
            curr.x() + v_in.x() * r / l_in,
            curr.y() + v_in.y() * r / l_in,
        )
        out_pt = QPointF(
            curr.x() + v_out.x() * r / l_out,
            curr.y() + v_out.y() * r / l_out,
        )
        if i == 0:
            path.moveTo(in_pt)
        else:
            path.lineTo(in_pt)
        path.quadTo(curr, out_pt)
    path.closeSubpath()
    return path


def _rounded_triangle_path(rect: QRectF, radius: float) -> QPainterPath:
    """Upward-pointing triangle inscribed in ``rect`` with rounded corners."""
    cx = rect.center().x()
    return _rounded_polygon(
        [
            QPointF(cx, rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ],
        radius,
    )


def _render_glyph_pixmap(theme: GlyphTheme, side_px: int) -> QPixmap:
    """Render ``theme`` (shape + symbol) into a fully-antialiased ``QPixmap``.

    The pixmap has full per-pixel alpha — there is no widget-level mask
    clipping the painted shape, so the antialiased edges bleed cleanly
    into transparency instead of stair-stepping at a hard region edge.
    """
    pixmap = QPixmap(side_px, side_px)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )

    inset = max(2.0, side_px * 0.06)
    rect = QRectF(inset, inset, side_px - 2 * inset, side_px - 2 * inset)

    if theme.shape == "triangle":
        # An upright triangle's optical centre sits below its geometric
        # centre — nudge the bounding box a touch so the "!" lands where
        # the eye expects it.
        rect.translate(0, side_px * 0.04)
        path = _rounded_triangle_path(rect, radius=side_px * 0.10)
    else:
        path = QPainterPath()
        path.addEllipse(rect)

    painter.setBrush(theme.fill)
    painter.setPen(QPen(theme.border, max(1.0, side_px * 0.035)))
    painter.drawPath(path)

    painter.setPen(theme.symbol_color)
    if theme.shape == "triangle":
        font = QFont("Helvetica", int(side_px * 0.46), QFont.Weight.Black)
        text_rect = QRectF(rect)
        text_rect.translate(0, side_px * 0.03)
    else:
        font = QFont("Helvetica", int(side_px * 0.5), QFont.Weight.Black)
        text_rect = QRectF(rect)
    painter.setFont(font)
    painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter), theme.symbol)

    painter.end()
    return pixmap


# ── inner glyph widget ─────────────────────────────────────────────────
class _GlyphIcon(QWidget):
    """A 64×64 child widget that paints the pre-rendered glyph pixmap.

    Mouse events are forwarded to the parent (which owns dismissal) by
    way of ``WA_TransparentForMouseEvents`` — the parent's ``setMask``
    decides what's clickable and what falls through.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(GLYPH_INNER, GLYPH_INNER)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pixmap: QPixmap | None = None

    def set_theme(self, theme: GlyphTheme) -> None:
        self._pixmap = _render_glyph_pixmap(theme, GLYPH_INNER)
        self.update()

    def paintEvent(self, event):  # noqa: N802 — Qt naming
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.drawPixmap(0, 0, self._pixmap)


# ── overlay window ─────────────────────────────────────────────────────
class GlyphOverlay(QWidget):
    """Transparent always-on-top window holding the glyph + optional tooltip.

    Emits :pyattr:`dismissed` when the user clicks the masked region (or
    after the auto-hide fade completes). Use :meth:`show_alert` to flash
    a level for ``duration_ms``.
    """

    dismissed = pyqtSignal(str)  # the level that was dismissed

    def __init__(
        self,
        position_mode: PositionMode = "top-right",
        play_chime: bool = False,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.BypassWindowManagerHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.resize(WINDOW_W, WINDOW_H)

        self._position_mode: PositionMode = position_mode
        self._play_chime = play_chime
        self._level: AlertLevel | None = None
        self._message: str = ""

        # Children -----------------------------------------------------
        self._icon = _GlyphIcon(self)
        self._icon_base_pos = QPoint((WINDOW_W - GLYPH_INNER) // 2, GLOW_PAD)
        self._icon.move(self._icon_base_pos)

        self._tooltip = QLabel(self)
        self._tooltip.setVisible(False)
        self._tooltip.setWordWrap(True)
        self._tooltip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tooltip.setMaximumWidth(320)
        self._tooltip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tooltip.setStyleSheet(
            "QLabel {"
            "  color: #fbf7f0;"
            "  background-color: rgba(0, 0, 0, 180);"
            "  border-radius: 14px;"
            "  padding: 8px 14px;"
            "  font-family: 'Helvetica Neue', 'Helvetica', sans-serif;"
            "  font-size: 14pt;"
            "  font-weight: 500;"
            "}"
        )

        # Soft outer glow effect for the phishing level (set up once,
        # toggled / re-coloured per-level via show_alert).
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setOffset(0, 0)
        self._glow.setBlurRadius(0.0)
        self._glow.setColor(self._glow_color(BRAND_CRIMSON))
        self._icon.setGraphicsEffect(self._glow)
        self._glow.setEnabled(False)

        # 1.4 s pulse: blur radius oscillates 12 → 32 → 12 with an in/out
        # sine so the glow breathes rather than blinks.
        self._glow_anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._glow_anim.setDuration(1400)
        self._glow_anim.setKeyValueAt(0.0, 12.0)
        self._glow_anim.setKeyValueAt(0.5, 32.0)
        self._glow_anim.setKeyValueAt(1.0, 12.0)
        self._glow_anim.setLoopCount(-1)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        # 2 s bob for ``suspicious``: a 4 px upward drift and back.
        self._bob_anim = QPropertyAnimation(self._icon, b"pos", self)
        self._bob_anim.setDuration(2000)
        self._bob_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._bob_anim.setLoopCount(-1)

        # Auto-hide and follow-cursor timers --------------------------
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self._begin_fade_out)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(60)
        self._cursor_timer.timeout.connect(self._reposition)

        # Fade animation: 350 ms ease-out cubic.
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(350)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._opacity_anim.finished.connect(self._on_anim_done)
        self._target_opacity_after_anim: float | None = None

        self._refresh_mask()

    # ── public API ────────────────────────────────────────────────
    def show_alert(
        self,
        level: AlertLevel,
        message: str = "",
        duration_ms: int = 5000,
    ) -> None:
        if level not in THEMES:
            raise ValueError(
                f"unknown level {level!r}; expected one of {list(THEMES)}"
            )
        theme = THEMES[level]
        self._level = level
        self._message = message
        self._icon.set_theme(theme)
        self._configure_motion(level, theme)
        self._configure_tooltip(message)
        self._reposition()
        self._refresh_mask()

        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            promote_to_panel(self, ignore_mouse=False)
            self._fade_to(1.0)
        else:
            self._fade_to(1.0)

        if self._position_mode == "follow-cursor":
            self._cursor_timer.start()

        self._auto_hide.start(max(1000, int(duration_ms)))

        if self._play_chime:
            _play_system_chime(level)

    def hide_alert(self) -> None:
        self._auto_hide.stop()
        self._cursor_timer.stop()
        self._begin_fade_out()

    # ── interaction ───────────────────────────────────────────────
    def mousePressEvent(self, event):  # noqa: N802
        # Any click within the masked region (glyph or tooltip) dismisses.
        self.hide_alert()

    # ── motion / tooltip / mask config ────────────────────────────
    def _configure_motion(self, level: str, theme: GlyphTheme) -> None:
        self._glow_anim.stop()
        self._bob_anim.stop()
        self._icon.move(self._icon_base_pos)

        if theme.glow is not None:
            self._glow.setColor(self._glow_color(theme.glow))
            self._glow.setBlurRadius(12.0)
            self._glow.setEnabled(True)
            self._glow_anim.start()
        else:
            self._glow.setEnabled(False)
            self._glow.setBlurRadius(0.0)

        if level == "suspicious":
            up = QPoint(self._icon_base_pos.x(), self._icon_base_pos.y() - 4)
            self._bob_anim.setKeyValueAt(0.0, self._icon_base_pos)
            self._bob_anim.setKeyValueAt(0.5, up)
            self._bob_anim.setKeyValueAt(1.0, self._icon_base_pos)
            self._bob_anim.start()

    def _configure_tooltip(self, message: str) -> None:
        text = (message or "").strip()
        if not text:
            self._tooltip.hide()
            self._tooltip.setText("")
            return
        self._tooltip.setText(text)
        # ``adjustSize`` honours both ``setMaximumWidth`` and word-wrap so
        # the pill is just-as-wide-as-it-needs.
        self._tooltip.adjustSize()
        hint = self._tooltip.sizeHint()
        width = max(80, min(320, hint.width()))
        height = self._tooltip.heightForWidth(width) if self._tooltip.wordWrap() else hint.height()
        if height <= 0:
            height = hint.height()
        self._tooltip.resize(width, height)
        x = (WINDOW_W - self._tooltip.width()) // 2
        y = self._icon_base_pos.y() + GLYPH_INNER + TOOLTIP_GAP
        self._tooltip.move(x, y)
        self._tooltip.show()

    def _refresh_mask(self) -> None:
        # Click-through everywhere except (a) the glyph + glow halo and
        # (b) the tooltip pill when shown. Both regions are *outside* the
        # painted antialiased silhouette of the glyph itself, so the
        # binary mask edge never lands on a pixel that we want anti-
        # aliased — the prior 1 px stair-stepping bug is gone.
        glyph_rect = QRect(
            self._icon_base_pos.x() - GLOW_PAD,
            self._icon_base_pos.y() - GLOW_PAD,
            GLYPH_INNER + 2 * GLOW_PAD,
            GLYPH_INNER + 2 * GLOW_PAD,
        )
        region = QRegion(glyph_rect, QRegion.RegionType.Ellipse)
        if self._tooltip.isVisible():
            region = region.united(QRegion(self._tooltip.geometry()))
        self.setMask(region)

    # ── geometry ──────────────────────────────────────────────────
    def _reposition(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        if self._position_mode == "follow-cursor":
            from PyQt6.QtGui import QCursor

            pos = QCursor.pos()
            target_x = pos.x() + 24 - self._icon_base_pos.x()
            target_y = pos.y() + 24 - self._icon_base_pos.y()
            self.move(target_x, target_y)
            return

        avail = screen.availableGeometry()
        margin_right = 24
        margin_top = 28
        glyph_right_in_window = self._icon_base_pos.x() + GLYPH_INNER
        target_x = avail.right() - margin_right - glyph_right_in_window
        target_y = avail.top() + margin_top - self._icon_base_pos.y()
        self.move(target_x, target_y)

    # ── animation plumbing ────────────────────────────────────────
    def _fade_to(self, target: float) -> None:
        self._opacity_anim.stop()
        self._target_opacity_after_anim = None
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(target)
        self._opacity_anim.start()

    def _begin_fade_out(self) -> None:
        self._cursor_timer.stop()
        self._target_opacity_after_anim = 0.0
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.start()

    def _on_anim_done(self) -> None:
        if self._target_opacity_after_anim == 0.0:
            level = self._level or "clear"
            self._glow_anim.stop()
            self._bob_anim.stop()
            self._tooltip.hide()
            self.hide()
            self._level = None
            self._target_opacity_after_anim = None
            self.dismissed.emit(level)

    # ── tiny helpers ──────────────────────────────────────────────
    @staticmethod
    def _glow_color(base: QColor) -> QColor:
        # Slightly translucent version of the brand colour so the glow
        # reads as a halo rather than an opaque stroke.
        return QColor(base.red(), base.green(), base.blue(), 200)


# ── audio (nice-to-have) ───────────────────────────────────────────────
_CHIME_BY_LEVEL: dict[str, str] = {
    "phishing": "/System/Library/Sounds/Sosumi.aiff",
    "suspicious": "/System/Library/Sounds/Funk.aiff",
    "clear": "/System/Library/Sounds/Glass.aiff",
}


def _play_system_chime(level: str) -> None:
    sound = _CHIME_BY_LEVEL.get(level)
    if not sound or not Path(sound).exists():
        return
    try:
        subprocess.Popen(  # noqa: S603, S607 — fixed system path
            ["/usr/bin/afplay", sound],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
