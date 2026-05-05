"""Tiny pub-sub bridge between sync skills and the async ``/ws`` endpoint.

The native overlay daemon and the Next.js panel both subscribe to ``/ws``
and listen for ``{"type": "alert", "level": ..., "message": ...}`` frames.
This module owns:

- ``_active_clients`` — a set of currently-connected WebSocket-like
  objects. Anything with an ``async send_json(payload)`` method works,
  which keeps tests trivial (no Starlette server needed).
- ``broadcast_alert(level, message)`` — fan out one frame to every client,
  dropping any socket that errors mid-send.
- ``broadcast_verdict_if_any()`` — pop the most recent ``analyze_email``
  verdict and broadcast it as a typed alert when it crosses the
  actionable threshold.

Splitting this out of ``main.py`` lets the smoke tests exercise the
bridge without importing FastAPI's full route surface (which has a hard
dependency on ``python-multipart`` via ``UploadFile``).
"""

from __future__ import annotations

from typing import Any, Protocol

from .skills import analyze_email as _analyze_email


class _SendJsonClient(Protocol):
    async def send_json(self, payload: dict[str, Any]) -> None: ...


# Module-level set of subscribers. Mutated by the ``/ws`` endpoint on
# accept / disconnect.
_active_clients: set[Any] = set()


# Verdict labels that warrant a UI alert. The spec uses "clear" as a
# synonym for our schema's "safe" — accept both.
ALERT_VERDICTS: tuple[str, ...] = ("phishing", "suspicious", "safe", "clear")
_VERDICT_LEVELS: dict[str, str] = {
    "phishing": "danger",
    "suspicious": "warning",
    "safe": "info",
    "clear": "info",
}


def register(client: _SendJsonClient) -> None:
    _active_clients.add(client)


def unregister(client: _SendJsonClient) -> None:
    _active_clients.discard(client)


def active_count() -> int:
    return len(_active_clients)


async def broadcast_alert(level: str, message: str) -> None:
    """Fan out an alert frame to every connected client.

    Any client whose ``send_json`` raises is removed from the registry —
    the next iteration stays clean even if the socket layer never told us
    the peer disappeared.
    """
    payload = {"type": "alert", "level": level, "message": message}
    dead: list[Any] = []
    for client in list(_active_clients):
        try:
            await client.send_json(payload)
        except Exception:  # noqa: BLE001 — any send error means we drop the client
            dead.append(client)
    for client in dead:
        _active_clients.discard(client)


async def broadcast_verdict_if_any() -> bool:
    """Pop the latest ``analyze_email`` verdict and broadcast it.

    Returns ``True`` if a verdict was broadcast, ``False`` otherwise (no
    stashed verdict, or verdict label below the actionable threshold).
    """
    stashed = _analyze_email.pop_last_verdict()
    if not stashed:
        return False
    verdict = (stashed.get("verdict") or "").lower()
    if verdict not in ALERT_VERDICTS:
        return False
    level = _VERDICT_LEVELS.get(verdict, "info")
    speak = (stashed.get("speak_aloud") or "").strip()
    signs = stashed.get("signs") or []
    headline = signs[0] if signs else f"verdict: {verdict}"
    message = speak or headline
    await broadcast_alert(level, message)
    return True
