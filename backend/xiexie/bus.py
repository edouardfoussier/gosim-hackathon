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
# Map every accepted verdict to the *overlay's* native vocabulary
# (``phishing`` / ``suspicious`` / ``clear``) so a single ``level`` value
# in the broadcast frame drives all three consumer surfaces:
#   - native PyQt6 overlay glyph (THEMES keyed by these labels)
#   - Next.js verdict banner
#   - any future Chrome extension consumer
# ``safe`` is normalised to ``clear`` for backward compat with the schema.
_VERDICT_LEVELS: dict[str, str] = {
    "phishing": "phishing",
    "suspicious": "suspicious",
    "safe": "clear",
    "clear": "clear",
}


def register(client: _SendJsonClient) -> None:
    _active_clients.add(client)


def unregister(client: _SendJsonClient) -> None:
    _active_clients.discard(client)


def active_count() -> int:
    return len(_active_clients)


async def _fanout(payload: dict[str, Any]) -> None:
    """Send ``payload`` to every connected client; drop any that error.

    Internal helper shared by :func:`broadcast_alert` and
    :func:`broadcast_speaking` (and any future typed broadcaster).
    """
    dead: list[Any] = []
    for client in list(_active_clients):
        try:
            await client.send_json(payload)
        except Exception:  # noqa: BLE001 — any send error means we drop the client
            dead.append(client)
    for client in dead:
        _active_clients.discard(client)


async def broadcast_alert(
    level: str,
    message: str,
    *,
    url_sandbox: dict[str, Any] | None = None,
) -> None:
    """Fan out an alert frame to every connected client.

    ``url_sandbox`` is the optional ``UrlSandboxData`` blob the
    VerdictCard renders inside the card body. Built by
    ``analyze_email._build_url_sandbox`` from the first ``check_url``
    report and the email's visible link text — None for verdicts
    without an actionable link (e.g. clear / safe).

    Any client whose ``send_json`` raises is removed from the registry —
    the next iteration stays clean even if the socket layer never told us
    the peer disappeared.
    """
    payload: dict[str, Any] = {"type": "alert", "level": level, "message": message}
    if url_sandbox:
        payload["url_sandbox"] = url_sandbox
    await _fanout(payload)


async def broadcast_point(x: int, y: int, label: str | None = None) -> None:
    """Fan out a ``point`` frame so the pointer overlay (PyQt6 ghost
    cursor) and the in-browser arrow can highlight ``(x, y)`` on the
    user's screen.

    Coordinates are **global macOS screen pixels** (top-left origin),
    already translated from the captured image's coordinate space by
    ``read_screen``. The browser caps a frontend-only "point" inside
    its viewport when needed; the native overlay paints anywhere.
    """
    payload: dict[str, Any] = {"type": "point", "x": int(x), "y": int(y)}
    if label:
        payload["label"] = label
    await _fanout(payload)


async def broadcast_working(state: str, label: str | None = None) -> None:
    """Fan out a ``working`` frame so subscribers can show a thinking
    indicator while the agent is silently busy (vision call, scam
    analysis, AppleScript automation, …).

    ``state`` is ``"start"`` or ``"stop"``. ``label`` is an optional
    human-readable hint (e.g. ``"reading your screen"``,
    ``"analysing the email"``) that the cursor halo can flash next to
    the bars and the status pill in the chat header can render.

    Distinct from ``speaking`` because the user-facing visuals differ:
    speaking = audio bars driven by RMS; working = soft indeterminate
    pulse. Both can be active simultaneously.
    """
    payload: dict[str, Any] = {"type": "working", "state": state}
    if label:
        payload["label"] = label
    await _fanout(payload)


async def broadcast_speaking(state: str, level: float | None = None) -> None:
    """Fan out a ``speaking`` frame to every connected client.

    ``state`` is ``"start"`` or ``"stop"``; ``level`` is an optional
    RMS amplitude in ``0..1`` that the native overlay uses to drive its
    soundwave bars (omit for procedural fallback).

    The browser's realtime client posts to ``POST /voice/speaking`` ~10×
    per second while gpt-realtime is producing audio; we forward straight
    through with no batching — the WS payload is tiny (~50 bytes) and
    smoothing happens on the consumer (``SoundwaveOverlay`` lerps its
    bars toward the target level).
    """
    payload: dict[str, Any] = {"type": "speaking", "state": state}
    if level is not None:
        payload["level"] = level
    await _fanout(payload)


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
    sandbox = stashed.get("url_sandbox") if isinstance(stashed, dict) else None
    await broadcast_alert(level, message, url_sandbox=sandbox)
    return True
