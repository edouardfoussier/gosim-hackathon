"""Background WebSocket client that bridges Xiexie backend → Qt signals.

Connects to ``ws://localhost:8787/ws`` (the same endpoint the Next.js app
uses) and forwards messages of shape::

    {"type": "alert", "level": "phishing"|"suspicious"|"clear", "message": "..."}

into a Qt signal that the overlay can react to from the main thread.

Other message types from the backend (``transcript``, ``speak``,
``skill_*``, ``done``, ``confirm``) are silently ignored — this client
is alert-only by design.

If the backend isn't reachable, the worker silently retries with
exponential backoff. The overlay's CLI test path (:mod:`overlay.demo`
``--level phishing``) does not depend on this client and works offline.
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
    """QObject that emits :pyattr:`alert` whenever the backend ships an alert.

    Signal payload: ``(level: str, message: str, raw: dict)``.
    """

    alert = pyqtSignal(str, str, dict)
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
        if payload.get("type") != "alert":
            return
        level = str(payload.get("level", "")).strip().lower()
        if level not in {"phishing", "suspicious", "clear"}:
            return
        message = str(payload.get("message", ""))
        self.alert.emit(level, message, payload)
