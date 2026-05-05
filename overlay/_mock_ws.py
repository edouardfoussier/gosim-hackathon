"""Tiny mock backend for end-to-end testing the overlay WS path.

Run::

    python -m overlay._mock_ws

Exposes ``ws://localhost:8787/ws`` and pushes one alert per second from
the cycle ``[phishing, suspicious, clear]`` to every connected client.

Not part of the production surface — keep around because the FastAPI
backend has a heavy dep tree (faster-whisper, torch on demand) that is
overkill for testing the overlay alone.
"""

from __future__ import annotations

import asyncio
import json
from itertools import cycle

from websockets.asyncio.server import serve


_LEVELS = cycle(
    [
        ("phishing", "Mock alert: this email looks like phishing."),
        ("suspicious", "Mock alert: a link in this email looks risky."),
        ("clear", "Mock alert: this email looks safe."),
    ]
)


async def _handle(ws):
    print(f"[mock-ws] client connected from {ws.remote_address}")
    try:
        while True:
            level, message = next(_LEVELS)
            payload = {"type": "alert", "level": level, "message": message}
            await ws.send(json.dumps(payload))
            print(f"[mock-ws] sent {payload}")
            await asyncio.sleep(2.5)
    except Exception as exc:  # noqa: BLE001
        print(f"[mock-ws] client gone: {exc!r}")


async def _main() -> None:
    async with serve(_handle, "127.0.0.1", 8787, process_request=_health_or_ws):
        print("[mock-ws] listening on ws://127.0.0.1:8787/ws")
        await asyncio.Future()  # run forever


async def _health_or_ws(connection, request):
    """Accept WS upgrade only on /ws; reject everything else."""
    if request.path != "/ws":
        from websockets.http11 import Response

        return Response(404, "Not Found", {}, b"only /ws is supported\n")
    return None


if __name__ == "__main__":
    asyncio.run(_main())
