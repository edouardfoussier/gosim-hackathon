"""Background WebSocket client that bridges Xiexie backend → Qt signals.

Connects to ``ws://localhost:8787/ws`` (the same endpoint the Next.js app
uses) and forwards two event types into Qt signals so the overlay can
react from the main thread:

- :pyattr:`alert` — payload ``(level: str, message: str, raw: dict)``,
  triggered by ``{"type": "alert", "level": "phishing"|"suspicious"|"clear",
  "message": "..."}``. Drives :class:`overlay.glyph.GlyphOverlay`.
- :pyattr:`speaking` — payload ``(state: str, level: float | None, raw: dict)``,
  triggered by ``{"type": "speaking", "state": "start"|"stop", "level": 0..1 | null}``.
  Drives :class:`overlay.soundwave.SoundwaveOverlay`.
- :pyattr:`working` — payload ``(state: str, label: str | None, raw: dict)``,
  triggered by ``{"type": "working", "state": "start"|"stop", "label": "..."}``.
  Lights up the soundwave in a calmer "thinking" mode while a skill
  runs silently (vision call, scam analysis, AppleScript automation).
- :pyattr:`point` — payload ``(x: int, y: int, label: str | None, raw: dict)``,
  triggered by ``{"type": "point", "x": 1240, "y": 820, "label": "..."}``.
  Drives :class:`overlay.pointer.PointerOverlay` — a ghost cursor that
  glides to (x, y) and flashes the label.

Other message types from the backend (``transcript``, ``speak``,
``skill_*``, ``done``, ``confirm``) are silently ignored — this bridge
is overlay-events-only by design.

If the backend isn't reachable, the worker silently retries with
exponential backoff. The overlay's CLI test paths
(:mod:`overlay.demo` ``--level phishing`` and
:mod:`overlay.soundwave` ``--procedural``) do not depend on this client
and work offline.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from websockets.asyncio.client import connect as ws_connect
except ImportError:  # pragma: no cover — websockets <14
    from websockets import connect as ws_connect  # type: ignore[no-redef]


DEFAULT_URL = "ws://localhost:8787/ws"


class WsBridge(QObject):
    """QObject that emits Qt signals for the two overlay event types.

    Signals:

    - :pyattr:`alert` — ``(level: str, message: str, raw: dict)`` for
      ``{"type": "alert", ...}`` frames.
    - :pyattr:`speaking` — ``(state: str, level: float | None, raw: dict)``
      for ``{"type": "speaking", ...}`` frames. ``level`` is ``None``
      when the backend payload omitted the field (procedural fallback).
    """

    alert = pyqtSignal(str, str, dict)
    # PyQt6 cannot pass ``None`` through a typed ``float`` slot; use the
    # generic ``object`` slot so the receiver can branch on
    # ``isinstance(level, float)`` cleanly.
    speaking = pyqtSignal(str, object, dict)
    working = pyqtSignal(str, object, dict)
    point = pyqtSignal(int, int, object, dict)
    connected = pyqtSignal(bool)

    def __init__(self, url: str = DEFAULT_URL, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── lifecycle ─────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="xiexie-overlay-ws", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Don't join — the thread is daemon and may be in a network read.

    # ── worker ────────────────────────────────────────────────────────
    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._loop())
        finally:
            loop.close()

    async def _loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with ws_connect(self._url, ping_interval=20) as ws:
                    self.connected.emit(True)
                    backoff = 1.0
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        self._dispatch(raw)
            except Exception as exc:  # noqa: BLE001
                self.connected.emit(False)
                # Avoid spamming logs: print only every ~10s of failure.
                if backoff <= 1.0:
                    print(f"[overlay.ws_client] disconnected ({exc!r}); retrying…")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.7, 10.0)
        self.connected.emit(False)

    def _dispatch(self, raw: str | bytes) -> None:
        try:
            payload: Any = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(payload, dict):
            return

        kind = payload.get("type")
        if kind == "alert":
            level = str(payload.get("level", "")).strip().lower()
            if level not in {"phishing", "suspicious", "clear"}:
                return
            message = str(payload.get("message", ""))
            self.alert.emit(level, message, payload)
            return

        if kind == "speaking":
            state = str(payload.get("state", "")).strip().lower()
            if state not in {"start", "stop"}:
                return
            raw_level = payload.get("level")
            level: float | None
            if raw_level is None:
                level = None
            else:
                try:
                    level = float(raw_level)
                except (TypeError, ValueError):
                    level = None
                else:
                    if level != level or level in (float("inf"), float("-inf")):
                        # NaN / inf — drop the amplitude, keep the state.
                        level = None
                    else:
                        level = max(0.0, min(1.0, level))
            self.speaking.emit(state, level, payload)
            return

        if kind == "working":
            state = str(payload.get("state", "")).strip().lower()
            if state not in {"start", "stop"}:
                return
            raw_label = payload.get("label")
            label = str(raw_label) if isinstance(raw_label, str) else None
            self.working.emit(state, label, payload)
            return

        if kind == "point":
            try:
                x = int(payload.get("x", 0))
                y = int(payload.get("y", 0))
            except (TypeError, ValueError):
                return
            raw_label = payload.get("label")
            label = str(raw_label) if isinstance(raw_label, str) else None
            self.point.emit(x, y, label, payload)
            return
