"""GlyphOverlay — a single transparent always-on-top widget that paints a
contextual warning glyph and fades out after a few seconds.

Three alert levels:
- ``phishing`` → red triangle with a centered ``!``
- ``suspicious`` → amber circle with a centered ``?``
- ``clear`` → green circle with a centered ``✓``

Three positioning modes:
- ``top-right`` (default) — fixed offset from the active screen's
  available top-right corner.
- ``follow-cursor`` — repositions on a 60ms timer to track ``QCursor.pos()``
  with a small offset, like Clicky's blue companion.
- ``near-active-window`` — *placeholder*; same as ``top-right`` until
  Accessibility API integration lands. See OVERLAY_README.md.

Click-through: the QWidget is full-screen-sized but uses :meth:`setMask`
so only the glyph polygon receives mouse events. Everything outside the
mask passes through to whatever app sits underneath.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import (
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygon,
    QRegion,
)
from PyQt6.QtWidgets import QApplication, QWidget

from .ns_panel import promote_to_panel

AlertLevel = Literal["phishing", "suspicious", "clear"]
PositionMode = Literal["top-right", "follow-cursor", "near-active-window"]


@dataclass(frozen=True)
class GlyphTheme:
    fill: QColor
    border: QColor
    text: QColor
    symbol: str
    shape: Literal["triangle", "circle"]
    label: str


THEMES: dict[str, GlyphTheme] = {
    "phishing": GlyphTheme(
        fill=QColor(220, 50, 47, 235),
        border=QColor(120, 20, 20, 255),
        text=QColor("white"),
        symbol="!",
        shape="triangle",
        label="Phishing",
    ),
    "suspicious": GlyphTheme(
        fill=QColor(255, 170, 30, 230),
        border=QColor(160, 90, 0, 255),
        text=QColor(70, 35, 0),
        symbol="?",
        shape="circle",
        label="Suspicious",
    ),
    "clear": GlyphTheme(
        fill=QColor(40, 170, 90, 220),
        border=QColor(20, 90, 40, 255),
        text=QColor("white"),
        symbol="✓",
        shape="circle",
        label="Clear",
    ),
}

_GLYPH_SIZE = QSize(180, 180)


class GlyphOverlay(QWidget):
    """Transparent always-on-top floating glyph.

    Emits :pyattr:`dismissed` when the user clicks the glyph (or it
    auto-hides). Use :meth:`show_alert` to flash a level for ``duration_ms``.
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
        # NOTE: do NOT set WA_TransparentForMouseEvents — we want the glyph
        # itself to be clickable. Click-through outside is handled via
        # ``setMask`` below.

        self._position_mode: PositionMode = position_mode
        self._play_chime = play_chime
        self._level: AlertLevel | None = None
        self._message: str = ""
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self._begin_fade_out)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(60)
        self._cursor_timer.timeout.connect(self._reposition)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(220)
        self._opacity_anim.finished.connect(self._on_anim_done)
        self._target_opacity_after_anim: float | None = None

        self.resize(_GLYPH_SIZE)

    # ── public API ────────────────────────────────────────────────────
    def show_alert(
        self,
        level: AlertLevel,
        message: str = "",
        duration_ms: int = 5000,
    ) -> None:
        if level not in THEMES:
            raise ValueError(f"unknown level {level!r}; expected one of {list(THEMES)}")
        self._level = level
        self._message = message
        self._reposition()
        self.update()

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

    # ── painting ──────────────────────────────────────────────────────
    def paintEvent(self, event):  # noqa: N802 — Qt naming
        if self._level is None:
            return
        theme = THEMES[self._level]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)
        path = _shape_path(theme.shape, rect)

        # soft drop shadow
        shadow = QPainterPath(path)
        painter.translate(2, 4)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(shadow)
        painter.translate(-2, -4)

        painter.setBrush(theme.fill)
        painter.setPen(QPen(theme.border, 3))
        painter.drawPath(path)

        painter.setPen(theme.text)
        painter.setFont(QFont("Helvetica", 80, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, theme.symbol)

    def resizeEvent(self, event):  # noqa: N802
        # Mask the input region to the visible glyph polygon so clicks
        # outside fall through to apps below.
        if self._level is None:
            self.clearMask()
            return
        rect = self.rect().adjusted(8, 8, -8, -8)
        if THEMES[self._level].shape == "triangle":
            tri = _triangle_polygon(rect)
            self.setMask(QRegion(tri))
        else:
            self.setMask(QRegion(rect, QRegion.RegionType.Ellipse))

    # ── interaction ───────────────────────────────────────────────────
    def mousePressEvent(self, event):  # noqa: N802
        # Any click on the visible glyph dismisses.
        self.hide_alert()

    # ── helpers ───────────────────────────────────────────────────────
    def _reposition(self) -> None:
        if self._position_mode == "follow-cursor":
            from PyQt6.QtGui import QCursor

            pos = QCursor.pos()
            self.move(pos.x() + 24, pos.y() + 24)
            return

        # default: top-right of the active screen
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        margin_right = 24
        margin_top = 60
        self.move(
            avail.right() - self.width() - margin_right,
            avail.top() + margin_top,
        )

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
            self.hide()
            self._level = None
            self._target_opacity_after_anim = None
            self.dismissed.emit(level)


# ── geometry helpers ───────────────────────────────────────────────────
def _triangle_polygon(rect: QRect) -> QPolygon:
    return QPolygon(
        [
            QPoint(rect.center().x(), rect.top() + 4),
            QPoint(rect.right() - 4, rect.bottom() - 4),
            QPoint(rect.left() + 4, rect.bottom() - 4),
        ]
    )


def _shape_path(shape: str, rect: QRect) -> QPainterPath:
    path = QPainterPath()
    if shape == "triangle":
        tri = _triangle_polygon(rect)
        p0, p1, p2 = tri.point(0), tri.point(1), tri.point(2)
        path.moveTo(float(p0.x()), float(p0.y()))
        path.lineTo(float(p1.x()), float(p1.y()))
        path.lineTo(float(p2.x()), float(p2.y()))
        path.closeSubpath()
    else:
        path.addEllipse(QRectF(rect))
    return path


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
